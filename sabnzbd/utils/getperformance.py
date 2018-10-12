import platform, subprocess
from .pystone import pystones


def getcpu():
    # find the CPU name (which needs a different method per OS), and return it
    # If none found, return platform.platform().

    cputype = None

    try:
        if platform.system() == "Windows":
            import winreg as winreg	# needed on Python 2
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Hardware\Description\System\CentralProcessor\0")
            cputype = winreg.QueryValueEx(key, "ProcessorNameString")[0]
            winreg.CloseKey(key)

        elif platform.system() == "Darwin":
            cputype = subprocess.check_output(['sysctl', "-n", "machdep.cpu.brand_string"]).strip()

        elif platform.system() == "Linux":
            for myline in open("/proc/cpuinfo"):
                if myline.startswith('model name'):
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
    try:
        return int(pystones(1000)[1])
    except:
        return None

    # if we arrive here, we were able to succesfully import pystone, so start calculation
    maxpystone = None
    # Start with a short run, find the the pystone, and increase runtime until duration took > 0.1 second
    for pyseed in [1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000]:
        duration, pystonefloat = pystones(pyseed)
        maxpystone = max(maxpystone, int(pystonefloat))
        # Stop when pystone() has been running for at least 0.1 second
        if duration > 0.1:
            break
    return maxpystone


if __name__ == '__main__':
    print((getpystone()))
    print((getcpu()))
