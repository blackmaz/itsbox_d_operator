@echo off

FOR /F %%P IN ('type %%TEMP%%\OpManager.pid') DO TASKKILL /F /T /PID %%P
