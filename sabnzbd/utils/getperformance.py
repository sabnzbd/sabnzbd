import platform
import subprocess


def getcpu():
    # find the CPU name (which needs a different method per OS), and return it
    # If none found, return platform.platform().

    cputype = None

    try:
        if platform.system() == "Windows":
            import _winreg as winreg	# needed on Python 2
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Hardware\Description\System\CentralProcessor\0")
            cputype = winreg.QueryValueEx(key, "ProcessorNameString")[0]
            winreg.CloseKey(key)

        elif platform.system() == "Darwin":
            cputype = subprocess.check_output(['sysctl', "-n", "machdep.cpu.brand_string"]).strip()

        elif platform.system() == "Linux":
            for myline in open("/proc/cpuinfo"):
                if myline.startswith(('model name')):
                    # Typical line:
                    # model name      : Intel(R) Xeon(R) CPU           E5335  @ 2.00GHz
                    cputype = myline.split(":", 1)[1]	# get everything after the first ":"
                    break # we're done
    except:
        # An exception, maybe due to a subprocess call gone wrong
        pass

    if cputype:
        # OK, found. Remove unnneeded spaces:
        cputype = " ".join(cputype.split())
    else:
        # Not found, so let's fall back to platform()
        cputype = platform.platform()

    return cputype


def getpystone():
    value = None
    for pystonemodule in ['test.pystone', 'pystone']:
        try:
            exec "from " + pystonemodule + " import pystones"
            value = int(pystones(1000)[1])
            break  # import and calculation worked, so we're done. Get out of the for loop
        except:
            pass  # ... the import went wrong, so continue in the for loop
    return value


if __name__ == '__main__':
    print getpystone()
    print getcpu()
