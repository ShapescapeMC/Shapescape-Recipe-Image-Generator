'''
This module implements the GUI for the application.
'''
from threading import Thread, Event
import tkinter as tk
from tkinter import ttk
from tkinter.filedialog import askopenfilename, askdirectory
from tkinter import messagebox
from pathlib import Path
import logging
from typing import List, Literal, Callable, NamedTuple

from .utils import TextureNotFound
from .project import (
    Project, get_interactive_mode, update_recipe_properties_md, initialize_project,
    update_recipe_properties_json, list_templates,
    get_app_data_path, set_interactive_mode)
from .cache import CachedSettings, push_database, force_pull_database
from .version import VERSION
from queue import Queue

class ProgressBarUpdate(NamedTuple):
    '''
    A data packet sent FROM the wroker thread TO the main (GUI) thread to
    update the progress bar that shows the progress of rendering the images.
    '''
    progress: int
    total: int

class InteractiveModeUpdate(NamedTuple):
    '''
    A data packet sent FROM the main (GUI) thread TO the worker thread to send
    the path selected by the user in interactive mode. The path can be None if
    the user cancels the selection.
    '''
    path: None | Path

class PathRequestUpdate(NamedTuple):
    '''
    A data packet sent FROM the worker thread TO the main (GUI) thread to
    request the path from the user.
    '''
    item_name: str
    data: int
    recipe_name: str

class GuiProjectApp(tk.Tk):
    '''
    The main GUI app object for the generator. It also servers as the
    controller in the MVC pattern.
    '''

    def __init__(
            self,
            cached_settings: None | CachedSettings = None,
            save_cache_after_exit: bool = True,
    ):
        super().__init__()
        # APP DISPLAY SETTINGS
        str_version = ".".join(str(i) for i in VERSION)
        self.title(f'Recipe Image Generator v{str_version}')
        self.minsize(width=1000, height=400)

        # SETUP MVC
        self.view = GuiProjectView(self)
        self.view.pack(expand=True, anchor='n', fill='both')
        self.project = Project()
        self.setup_project_interactive_texture_getter()

        # DEBUG
        # Used to disable saving after run
        self.save_cache_after_exit = save_cache_after_exit

        # THREADING
        # Task thread
        self.worker_thread: None | Thread = None
        # Queues for sending data between the worker and the main threads
        self.progress_bar_update_queue: Queue[ProgressBarUpdate] = Queue()
        # Sends the paths selected by user from main to the worker thread
        self.interactive_mode_queue: Queue[InteractiveModeUpdate] = Queue()
        # Sends the path selection request from worker to the main thread
        self.request_path_queue: Queue[PathRequestUpdate] = Queue(maxsize=1)

        # The stop event for stoping the working thread
        self.stop: Event = Event()

        # LOADING CACHED SETTINGS
        if cached_settings is None:
            cached_settings = CachedSettings.from_settings_file()
        # Copy settings to the project
        if cached_settings.behavior_pack_path is not None:
            self.project.behavior_pack = cached_settings.behavior_pack_path
        else:
            self.project.behavior_pack = Path("")

        if cached_settings.resource_pack_path is not None:
            self.project.resource_pack = cached_settings.resource_pack_path
        else:
            self.project.resource_pack = Path("")

        if cached_settings.local_data_path is not None:
            self.project.local_data = cached_settings.local_data_path
        else:
            self.project.local_data = Path("")

        if cached_settings.image_scale is not None:
            self.project.scale = cached_settings.image_scale
        else:
            self.project.scale = 1

        # Copy settings into the view (GUI)
        self.view.rp_path.set(
            "" if self.project.resource_pack is None
            else self.project.resource_pack.as_posix())
        self.view.bp_path.set(
            "" if self.project.behavior_pack is None
            else self.project.behavior_pack.as_posix())
        self.view.local_data_path.set(
            "" if self.project.local_data is None
            else self.project.local_data.as_posix())
        self.view.scale.set(str(self.project.scale))

        # Update the template selection menu (GUI)
        self.view.update_template_menu_button()

    def __enter__(self):
        '''
        Required for using the app as a context manager (in with statement).
        '''
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        '''
        Runs when the app is closed when used as a context manager (in with
        statement).
        '''
        # STOP THE WORKING THREAD IF IT IS RUNNING
        self.stop.set()
        # Send a dummy update to the worker thread for a rare case when it is
        # waiting for the user to select a path
        self.interactive_mode_queue.put(InteractiveModeUpdate(None), block=False)
        if self.worker_thread is not None:
            self.worker_thread.join()
        # SAVE CACHED SETTINGS
        self.save_cached_settings()

    def setup_project_interactive_texture_getter(self):
        def worker_request_path(
                item_name: str, data: int, recipe_name: str) -> Path:
            '''
            Requests the path from the user and sends it to the worker thread.
            '''
            self.request_path_queue.put(PathRequestUpdate(
                item_name=item_name, data=data, recipe_name=recipe_name))
            update = self.interactive_mode_queue.get()
            if update.path is None:
                raise TextureNotFound(
                    f"User didn't provide a valid texture for: "
                    f"{item_name}:{data}.")
            return update.path
        self.project.interactive_texture_getters.append(worker_request_path)

    def save_cached_settings(self):
        self.update_from_gui()
        if self.save_cache_after_exit:  # This is for debugging
            CachedSettings(
                resource_pack_path=self.project.resource_pack,
                behavior_pack_path=self.project.behavior_pack,
                local_data_path=self.project.local_data,
                image_scale=self.project.scale,
            ).save()

    def update_from_gui(self):
        set_interactive_mode(self.view.interactive_mode.get())
        self.project.scale = self.view.get_scale()
        self.project.template = self.view.template.get()
        self.project.resource_pack = (
            Path(self.view.rp_path.get())
            if self.view.rp_path.get() != "" else None)
        self.project.behavior_pack = (
            Path(self.view.bp_path.get())
            if self.view.bp_path.get() != "" else None)
        self.project.local_data = (
            Path(self.view.local_data_path.get())
            if self.view.local_data_path.get() != "" else None)

    def start_generating(self) -> None:
        '''
        Starts the thread that generates the images if there is no other thread
        running in the background.
        '''

        # CHECK FOR ANOTHER THREAD
        if self.worker_thread is not None:
            self.view.error_dialog('There is another job in progress.')
            return


        # LOAD THE SETTINGS
        self.update_from_gui()
        self.save_cached_settings()
        # Print info abot the job that is about to start
        logging.info(
            "\n==============================================\n"
            f'Interactive mode: {get_interactive_mode()}\n'
            f'Behavior pack: {self.project.behavior_pack}\n'
            f'Resource pack: {self.project.resource_pack}\n'
            f'App data: {self.project.global_data}\n'
            f'Project data: {self.project.local_data}\n'
            "==============================================")
        # RUN THE JOB ONLY IF THE PROJECT IS SET UP
        if (
                self.project.local_data is None or
                self.project.behavior_pack is None or
                self.project.resource_pack is None):
            self.view.error_dialog('Please set up the project first.')
            return

        # DISABLE GUI
        self.view.set_gui_state("disabled")
        logging.info("Preparing job to perform...")

        # START THE THREAD
        self.worker_thread = Thread(target=self.threaded_generate)
        self.worker_thread.start()
        self.after(100, self.watch_thread_generate)

    def dump_variables(self):
        try:
            json_path = self.project.local_data / "recipe_properties.json"
            md_path = self.project.local_data / "recipe_properties.md"
            message = update_recipe_properties_md(json_path, md_path)
            messagebox.showinfo(
                title="Info", message=message)
        except ValueError as e:
            messagebox.showerror(
                title="Error", message=str(e))

    def create_workspace_files(self):
        initialize_project(self.project.local_data)
        update_recipe_properties_json(
            self.project.local_data / "recipe_properties.json",
            self.project.behavior_pack)
        self.view.update_template_menu_button()

    def threaded_generate(self):
        '''
        The function that is run in a separate thread to generate the images.
        '''
        # GET THE JOB STEPS AS A LIST
        recipe_paths = self.project.get_recipe_paths_list()
        job_steps: List[Callable[[], None]] = list(
            self.project.yield_book_creation_aciton(recipe_paths))

        # RUN THE JOB, KEEP UPDATING THE QUEUE WITH INFO FOR THE GUI
        logging.info("Generating...")
        total = len(job_steps)
        for i, action in enumerate(job_steps):
            # CHECK FOR STOPPING THE THREAD
            if self.stop.is_set():
                return
            # RUN JOB STEP
            action()
            # UPDATE GUI
            self.progress_bar_update_queue.put(ProgressBarUpdate(i, total))

    def watch_thread_generate(self):
        '''
        The function that is run in the main thread to watch the progress of
        the thread that is generating the images.
        '''
        # CHECK THE GUI UPDATE QUEUE
        while not self.progress_bar_update_queue.empty():
            data: ProgressBarUpdate = self.progress_bar_update_queue.get()
            self.view.update_progress_bar_info(f"{data.progress}/{data.total}")
            self.view.set_progress(data.progress / data.total)
        # CHECK THE PATH REQUEST QUEUE
        while not self.request_path_queue.empty():
            data: PathRequestUpdate = self.request_path_queue.get()
            dialog = ResourcePathSelectionDialog(
                self.view,
                data.item_name,
                data.data,
                data.recipe_name,
                self.project.resource_pack,
                self.project.local_data)
            if dialog.result_approved:
                self.interactive_mode_queue.put(
                    InteractiveModeUpdate(Path(dialog.result).resolve()))
            else:
                self.interactive_mode_queue.put(
                    InteractiveModeUpdate(None))
        # CHECK IF THE THREAD IS STILL RUNNING, AND SCHEDULE NEXT CHECK
        if self.worker_thread and self.worker_thread.is_alive():
            self.after(100, self.watch_thread_generate)
        else:
            # Cleanup after performing the job
            self.worker_thread = None
            self.view.update_progress_bar_info("Pushing changes to Github...")
            push_database()
            self.view.set_progress(0)
            self.view.set_gui_state("normal")
            self.view.update_progress_bar_info("")

    def start_syncing_database(self):
        '''
        Starts the thread that syncs the database if there is no other thread
        running in the background.
        '''
        if self.worker_thread is not None:
            self.view.error_dialog('There is another job in progress.')
            return
        self.view.set_gui_state('disabled')

        self.worker_thread = Thread(target=force_pull_database)
        self.worker_thread.start()
        self.after(100, self.watch_thread_sync_database)
    
    def watch_thread_sync_database(self):
        '''
        The function that is run in the main thread to watch the progress of
        the thread that is syncing the database.
        '''
        if self.worker_thread and self.worker_thread.is_alive():
            self.after(100, self.watch_thread_sync_database)
        else:
            self.worker_thread = None
            messagebox.showinfo(title="Info", message="All synced!")
            self.view.update_template_menu_button()
            self.view.set_gui_state('normal')

class GuiProjectView(ttk.Frame):
    def __init__(self, parent: GuiProjectApp):
        super().__init__(parent)

        # The parent (GuiProjectApp) is the controller as well
        self.app = parent

        self.rp_path = tk.StringVar()
        self.bp_path = tk.StringVar()
        self.local_data_path = tk.StringVar()

        # generate button
        self.sync_button = ttk.Button(
            self, text='Sync Database',
            command=lambda: self.app.start_syncing_database())
        self.sync_button.pack(expand=False, side='top', fill='x')

        # Input paths
        input_paths = ttk.Frame(self)
        input_paths.pack(side='top', expand=False, fill='x')

        input_path_labels = ttk.Frame(input_paths)
        input_path_labels.pack(side='left', expand=False, fill='both')
        ttk.Label(input_path_labels, text="Resource pack:").grid(
            row=0, column=0, sticky='w', padx=5, pady=2)
        ttk.Label(input_path_labels, text="Behavior pack:").grid(
            row=1, column=0, sticky='w', padx=5, pady=2)
        ttk.Label(input_path_labels, text="Working directory:").grid(
            row=2, column=0, sticky='w', padx=5, pady=2)

        input_path_entries = ttk.Frame(input_paths)
        input_path_entries.pack(side='left', expand=True, fill='both')
        self.rp_path_entry = ttk.Entry(
            input_path_entries, textvariable=self.rp_path, width=45)
        self.rp_path_entry.pack(side='top', expand=True, fill='x', padx=5)

        self.bp_path_entry = ttk.Entry(
            input_path_entries, textvariable=self.bp_path, width=45)
        self.bp_path_entry.pack(side='top', expand=True, fill='x', padx=5)

        self.local_data_path_entry = ttk.Entry(
            input_path_entries, textvariable=self.local_data_path, width=45)
        self.local_data_path_entry.pack(side='top', expand=True, fill='x', padx=5)

        input_path_buttons = ttk.Frame(input_paths)
        input_path_buttons.pack(side='right', expand=False, fill='both')
        self.rp_path_button = ttk.Button(
            input_path_buttons, text='Open',
            command=self.on_rp_path_button_pressed)
        self.rp_path_button.grid(row=0, column=0, columnspan=2, sticky="NSEW")

        self.bp_path_button = ttk.Button(
            input_path_buttons, text='Open',
            command=self.on_bp_path_button_pressed)
        self.bp_path_button.grid(row=1, column=0, columnspan=2, sticky="NSEW")

        self.local_data_path_button = ttk.Button(
            input_path_buttons, text='Open',
            command=self.on_local_data_path_button_pressed)

        self.local_data_path_button.grid(row=2, column=0)
        self.local_data_init_button = ttk.Button(
            input_path_buttons, text='Initialize',
            command=lambda: self.app.create_workspace_files())
        self.local_data_init_button.grid(row=2, column=1)

        # Settings (Template selection / size)
        settings = ttk.Frame(self)
        settings.pack(side='top', expand=False, fill='both')

        templates_frame = ttk.Frame(settings)
        templates_frame.pack(side='left', expand=False, fill='both')
        ttk.Label(templates_frame, text='Template:').pack(
            side='left', expand=False, fill='x', padx=5, pady=2)
        self.template = tk.StringVar()
        self.template_menu_button = ttk.OptionMenu(
            templates_frame, self.template, "")
        self.template_menu_button.config(width=20)
        self.template_menu_button.pack(side='left', expand=False, fill='x')

        settings_im_scale = ttk.Frame(settings)
        settings_im_scale.pack(side='right', expand=False, fill='both')
        ttk.Label(settings_im_scale, text='Image scale:').grid(row=0, column=0, sticky='ne', padx=5, pady=2)
        self.scale = tk.StringVar(value='1')
        self.scale_spinbox = ttk.Spinbox(
            settings_im_scale, from_=1, to=20,
            textvariable=self.scale,
            takefocus=False)
        self.scale_spinbox.grid(row=0, column=1, sticky='ne', padx=5, pady=2)

        # Interactive mode
        checkbox_frame = ttk.Frame(self)
        checkbox_frame.pack(side='top', expand=True, fill='both')
        self.interactive_mode = tk.BooleanVar(value=True)
        self.interactive_mode_checkbutton = ttk.Checkbutton(
            checkbox_frame, text='Interactive mode',
            variable=self.interactive_mode)
        self.interactive_mode_checkbutton.pack(side='top', expand=False, fill='x')

        # Progress bar info
        self.progres_bar_label = ttk.Label(self, text="", width=100)
        self.progres_bar_label.pack(side='bottom', expand=False, fill='x')

        # Progress bar
        self.progress_bar = ttk.Progressbar(self, maximum=1)
        self.progress_bar.pack(expand=False, side='bottom', fill='x')
        # self.set_progress(0.66)

        # generate button
        self.generate_button = ttk.Button(
            self, text='Generate', command=lambda: self.app.start_generating())
        self.generate_button.pack(expand=False, side='bottom', fill='x')

        # dump variables
        self.dump_variables_button = ttk.Button(
            self, text='Export Text',
            command=lambda: self.app.dump_variables())
        self.dump_variables_button.pack(expand=False, side='bottom', fill='x')


    def get_scale(self) -> int:
        try:
            scale = int(self.scale.get())
            if scale > 20:
                scale = 20
                self.scale.set('20')
            elif scale < 1:
                scale = 1
                self.scale.set('1')
            return scale
        except ValueError:
            self.scale.set('1')
            return 1

    def set_progress(self, progress: float) -> None:
        self.progress_bar.config(value=progress)

    def error_dialog(self, message: str) -> None:
        messagebox.showerror(title='Error', message=message)

    def update_template_menu_button(self) -> None:
        template_roots: List[Path] = [
            self.app.project.global_data / "templates",
            self.app.project.local_data / "templates"
        ]
        template_paths = list_templates(*template_roots)

        self.template_menu_button["menu"].delete(0, "end")
        for t in template_paths:
            # This t=t in lambda expression is such a brilliant hack.
            self.template_menu_button["menu"].add_command(
                label=t, command=lambda t=t: self.template.set(t))
        # Set the default value
        self.template.set(template_paths[0])

    def set_gui_state(self, state: Literal['disabled', 'normal']) -> None:
        '''
        Sets the state of GUI to 'disabled' or 'normal' (enabled). GUI is
        usually disabled when the program is running some background task.
        '''
        self.sync_button.config(state=state)
        self.dump_variables_button.config(state=state)
        self.generate_button.config(state=state)
        self.interactive_mode_checkbutton.config(state=state)
        self.local_data_init_button.config(state=state)
        self.scale_spinbox.config(state=state)  # type: ignore
        self.rp_path_entry.config(state=state)  # type: ignore
        self.bp_path_entry.config(state=state)  # type: ignore
        self.local_data_path_entry.config(state=state)
        self.rp_path_button.config(state=state)
        self.bp_path_button.config(state=state)
        self.local_data_path_button.config(state=state)
        self.template_menu_button.config(state=state)

    def update_progress_bar_info(self, text: str) -> None:
        self.progres_bar_label.config(text=text)

    def on_rp_path_button_pressed(self) -> None:
        initialdir = '.'
        if self.rp_path != "" and Path(self.rp_path.get()).exists():
            initialdir = self.rp_path.get()
        target = askdirectory(initialdir=initialdir)
        if target != "":
            self.rp_path.set(target)
            self.app.save_cached_settings()

    def on_bp_path_button_pressed(self) -> None:
        initialdir = '.'
        if self.bp_path != "" and Path(self.bp_path.get()).exists():
            initialdir = self.bp_path.get()
        target = askdirectory(initialdir=initialdir)
        if target != "":
            self.bp_path.set(target)
            self.app.save_cached_settings()

    def on_local_data_path_button_pressed(self) -> None:
        initialdir = '.'
        if self.local_data_path != "" and Path(self.local_data_path.get()).exists():
            initialdir = self.local_data_path.get()
        target = askdirectory(initialdir=initialdir)
        if target != "":
            self.local_data_path.set(target)
            self.app.save_cached_settings()

class ResourcePathSelectionDialog(tk.Toplevel):
    def __init__(
            self, master_view: GuiProjectView,
            item_name: str, item_data: int, recipe_name: str,
            resource_pack: Path, workspace_path: Path):
        '''
        Custom finding the path to an item texture.

        :param master_view: the parent window
        :parma item_name: the name of the item
        :param item_data: the data value of the item
        :param recipe_name: the name of the recipe
        :param resource_pack: the path to the resource pack
        :param workspace_path: the path to the workspace
        '''
        super().__init__(master_view, border=5)
        self.result = ""
        self.result_approved = False

        self.master_view = master_view

        self.attributes('-topmost', 'true')
        self.title(f"Missing texture!")
        # Outer label
        style = ttk.Style()
        style.configure("bold.TLabel", font=('Arial', 11, 'bold'))
        text_frame = ttk.Frame(self)
        text_frame.pack(side='top', expand=True, fill='x', padx=5, pady=5)

        label = ttk.Label(text_frame, text=f"Cannot find the texture of")
        label.pack(side='left')
        label = ttk.Label(text_frame, text=f"{item_name}:{item_data}", style="bold.TLabel")
        label.pack(side='left')
        label = ttk.Label(text_frame, text="for recipe")
        label.pack(side='left')
        label = ttk.Label(text_frame, text=f"{recipe_name}", style="bold.TLabel")
        label.pack(side='left')

        # The frame for all of the other stuff
        im_frame = ttk.Frame(self)
        im_frame.pack(side='top', fill='both', expand=True)
        im_interaction_frame_frame = ttk.Frame(im_frame)
        im_interaction_frame_frame.pack(side='top', expand=False, fill='both')

        im_interaction_frame = ttk.Frame(
            im_interaction_frame_frame)
        im_interaction_frame.pack(side='top', expand=True, fill='both')
        # Inner label
        im_message = ttk.Label(
            im_interaction_frame,
            text="Please use the buttons to find the path of the texutre"
        )
        im_message.pack(side='top', expand=False, fill='x', padx=5, pady=5)

        # Top buttons row
        # Button 1
        initialdir = (get_app_data_path() / "data/RP").resolve().as_posix()
        title = f'Looking for "{item_name}:{item_data}" in vanilla RP...'

        im_path_selection_buttons = ttk.Frame(im_interaction_frame)
        im_path_selection_buttons.pack(side='top', expand=False, fill='x')
        im_serch_default_rp_button = ttk.Button(
            im_path_selection_buttons, text='Vanilla RP',
            command=self.get_find_texture_func(
                initialdir, title, prefix="RP")
        )
        im_serch_default_rp_button.pack(
            side='left', expand=True, fill='x', padx=5)

        # Button 2
        initialdir = resource_pack.resolve().as_posix()
        im_search_project_block_button = ttk.Button(
            im_path_selection_buttons, text='Project RP',
            command=self.get_find_texture_func(
                initialdir,
                f'Looking for "{item_name}:{item_data}" in project RP...',
                prefix="RP")
        )
        # Button 3
        initialdir = (
            get_app_data_path() / "data/block-images").resolve().as_posix()
        title = f'Looking for "{item_name}:{item_data}" in vanilla block images...'
        im_search_project_block_button.pack(
            side='left', expand=True, fill='x', padx=5)
        im_search_default_block_button = ttk.Button(
            im_path_selection_buttons, text='Vanilla block image',
            command=self.get_find_texture_func(
                initialdir, title, prefix="block-images")
        )
        im_search_default_block_button.pack(
            side='left', expand=True, fill='x', padx=5)
        # Button 4
        initialdir = (
            workspace_path / "block-images").resolve().as_posix()
        im_search_project_rp_button = ttk.Button(
            im_path_selection_buttons, text='Project block image',
            command=self.get_find_texture_func(
                initialdir,
                f'Looking for "{item_name}:{item_data}" in project block images...',
                prefix="block-images")
        )
        im_search_project_rp_button.pack(
            side='left', expand=True, fill='x', padx=5)
        # Entry
        self.selected_path_label = ttk.Label(
            im_interaction_frame,
            text="Path not selected.", style="bold.TLabel")
        self.selected_path_label.pack(
            side='top', expand=False, fill='x', padx=5, pady=5)

        # The approve button
        self.im_approve_button = ttk.Button(
            self, text='Approve', command=self.approve_button_pressed)
        self.im_approve_button.pack(
            side='bottom', expand=False, fill='x', padx=5)
        self.im_approve_button.config(state='disabled')

        # Bottom buttons row
        im_path_approve_buttoms = ttk.Frame(self)
        im_path_approve_buttoms.pack(side='bottom', expand=False, fill='x', pady=5)
        self.im_ignore_button = ttk.Button(
            im_path_approve_buttoms, text='Ignore',
            command=self.ignore_button_pressed)
        self.im_ignore_button.pack(side='left', expand=True, fill='x', padx=5)
        self.im_ignore_all_button = ttk.Button(
            im_path_approve_buttoms, text="Ignore all",
            command=self.ignore_all_button_pressed)
        self.im_ignore_all_button.pack(side='left', expand=True, fill='x', padx=5)

        self.wait_window()

    def update_result_button(self):
        if self.result == "":
            self.im_approve_button.config(state='disabled')
        else:
            self.im_approve_button.config(state='normal')

    def approve_button_pressed(self):
        self.result_approved = True
        self.destroy()

    def ignore_button_pressed(self):
        self.result_approved = False
        self.destroy()
    
    def ignore_all_button_pressed(self):
        self.master_view.interactive_mode.set(False)
        set_interactive_mode(False)
        self.result_approved = False
        self.destroy()

    def get_find_texture_func(
            self, initialdir: str, title: str,
            prefix: str) -> Callable[..., None]:
        def result():
            self.attributes('-topmost', 'false')
            initialdir_path = Path(initialdir)
            initialdir_path.mkdir(parents=True, exist_ok=True)
            path = askopenfilename(
                initialdir=initialdir, title=title,
                filetypes=[("Images", ".png .jpg .jpeg .bmp")])
            path = Path(path)
            if not path.is_relative_to(initialdir_path):
                self.selected_path_label.config(
                    text=(
                        "Invalid path! Please select a path relative to "
                        "the folder opened in the file dialog."))
                self.result = ""
            else:
                short_path = path.relative_to(initialdir_path)
                formatted_path = (Path(prefix) / short_path).as_posix()
                self.selected_path_label.config(
                    text=f"Selected path: {formatted_path}")
                self.result = path
            self.update_result_button()
            self.attributes('-topmost', 'true')
        return result
