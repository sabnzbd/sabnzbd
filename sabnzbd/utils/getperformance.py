def getcpu():
    # On Linux, let's get the CPU model name:
    cputype = None
    try:
        for myline in open("/proc/cpuinfo"):
            if myline.startswith(('model name')):
                cputype = myline[13:].rstrip()
                break
    except:
        # probably not on Linux
        pass
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
