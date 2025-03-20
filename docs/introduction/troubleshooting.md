(troubleshooting)=
# Troubleshooting
This page explains how to solve the problems that you may
encounter when using the application.

## The application doesn't start
1. Check if it's properly installed. Follow the steps from the
  {ref}`Installation<installation>` section. After the installation,
  restart your console (powershell or command prompt).
2. If running the application in the console, prints some messages to console,
  but the GUI is not visible try deleting its cache. The data of the
  application (including the recipe-image-generator-data repository) is stored
  in `%userprofile%/AppData/Local/Shapescape/recipe-image-generator`.
