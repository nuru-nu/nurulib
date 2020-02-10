"""Hot plugs Python code into interactive environment / running scripts.

Synopsis:
    from smanmi import hotplug

    # As would be used for `importlib.import_module()`.
    module = hotplug.HotPlug('.hotplug.module')

    # This would result in a re-load if the module file has changed.
    print(module.value)
"""

import importlib, inspect, logging, os, traceback


class HotPlug:

    def __init__(self, name: str, logger: logging.Logger, autoreload=True):
        """Reloads module automatically when changes happened.

        If `autoreload=False`, then the module can still be reloaded if changes
        occurred by calling `hotplug_reload()`.
        """
        self._autoreload = autoreload
        self._logger = logger
        self._package = (
            inspect.getmodule(inspect.stack()[1].frame).__package__)
        self._module_name = name
        self._reload_mtime = None
        self._module = importlib.import_module(
            self._module_name, self._package)
        self._path = self._module.__file__
        self._reload_mtime = os.path.getmtime(self._path)

    def hotplug_reload(self):
        mtime = os.path.getmtime(self._path)
        if mtime == self._reload_mtime:
            return
        try:
            self._reload_mtime = os.path.getmtime(self._module.__file__)
            importlib.reload(self._module)
        except Exception as e:
            self._logger.warn('Cannot eval {}{} : {}'.format(
                self._module_name, self._package, e))
            self._logger.info('-' * 72)
            self._logger.info(traceback.format_exc())
            self._logger.info('-' * 72)

    def __getattr__(self, name):
        if self._autoreload:
            self.hotplug_reload()
        return getattr(self._module, name)

