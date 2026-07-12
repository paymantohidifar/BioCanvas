## Instructions

* Package name must be updated from `biosynic` to `biocanvas` and all dependencies must be updated accordingly.
* Two modules `pagoda` and `project_b` (renamed from `safari`) must be renamed. Come up with creative project names for them. Also, all imports must be resolved accordingly. Including tests.
* `bifrost` module is no longer available. All modules are now placed inside `src` directory. As such, all import dependencies must be resolved inlcusing tests.
* At this stage, keep unstracked files untracked by git. Once we update all namings and dependencies, we will starting version controlling them.
* Add requored missing dependencies to `pixi.toml` file.

## Replacing MSDrive package with local alternative

`MSDrive` library handles two-way communication with MS Sharepoint drive. We want to setup a local database so we can pull data from.


## Replacing `ui.ipynb` with a StreamLit dashboard

All ui components now should be compatible with depolying the ui using StreamLit.