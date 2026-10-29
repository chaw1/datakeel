# Local type declarations

Pyright discovers this directory by default. These partial, independently written
declarations describe the pytest-xdist 3.8.0 interfaces consumed by the test scheduler;
they contain no runtime implementation. The loadgroup declaration includes the
inherited loadscope members used by the scheduler and its focused tests.

The worker gateway is described structurally by its string identity because that is
the only gateway member consumed here. Review these declarations against the installed
source when upgrading pytest-xdist. They do not change type-checking thresholds or
replace the installed package at runtime.
