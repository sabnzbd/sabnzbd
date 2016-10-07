=== Table of contents ===

--- Introduction ---
--- Installing the pre-built Windows version ---
--- Installing the pre-built Mac OS X version ---
--- Installing the pre-built Linux version ---
--- Building and installing on UNIX type systems ---
--- Building and installing on Mac OS X systems ---
--- Building and installing on Windows operating systems ---
--- Building and installing on FreeBSD ---
--- Technical Details ---
--- Version History ---

=== Table of contents ===



--- Introduction ---


This is a concurrent (multithreaded) version of par2cmdline 0.4, a utility to
create and repair data files using Reed Solomon coding. par2 parity archives
are commonly used on Usenet postings to allow corrupted postings to be
repaired instead of needing the original poster to repost the corrupted
file(s).

For more information about par2, go to this web site:

http://parchive.sourceforge.net/

The original version of par2cmdline 0.4 was downloaded from:

http://sourceforge.net/projects/parchive


This version has been modified to utilise the Intel Threading Building Blocks
library, which enables it to process files concurrently instead of the
original version's serial processing. Computers with more than one CPU or core
such as those using Intel Core Duo, Intel Core Duo 2, or AMD Athlon X2 CPUs
can now create or repair par2 archives much quicker than the original version.
For example, dual core machines can achieve near-double performance when
creating or repairing.

The Intel Threading Building Blocks library is obtained from:

http://osstbb.intel.com/


The licensing of this source code has not been modified: it is still published
under the GPLv2 (or later), and the COPYING file is included in this
distribution as per the GPL.


To download the source code or some operating system builds of the
concurrent version of par2cmdline 0.4, go to:

http://www.chuchusoft.com/par2_tbb


--- Installing the pre-built Windows version ---


The Windows version is distributed as an executable (par2.exe) which has
built into it (i.e., statically linked) the Intel Threading Building Blocks
4.3 Update 1 library, built from the tbb43_20141023oss_src.tgz distribution.
The Windows version is portable (can be run from a USB thumb drive) and does
not require a specific version of the C runtime library because the par2.exe
executable is built by statically linking with the C runtime library.

To install, copy the par2.exe file and then invoke it from the command line.

To uninstall, delete the par2.exe file along with any files from the
distribution folder.


--- Installing the pre-built Mac OS X version ---


The Mac version is an universal build of the concurrent version of par2cmdline 0.4
for Mac OS X 10.5. In other words, the par2 executable file contains both a 32-bit
x86 and a 64-bit x86_64 build of the par2 sources. It is also portable and can be
run from a USB thumb drive (no need to copy to the Mac's internal storage device).

It is distributed as an executable (par2) along with the required universal build
of the Intel Threading Building Blocks 4.3 Update 1 library (libtbb.dylib).

To install, place the par2 and libtbb.dylib files in a folder and
invoke them from the command line.

To uninstall, delete the par2 and libtbb.dylib files along with any
files from the distribution folder.


--- Installing the pre-built Linux version ---


The Linux versions are a 32-bit i386 and 64-bit x86_64 build of the
concurrent version of par2cmdline 0.4 for GNU/Linux kernel version 2.6
with GCC 4. It is distributed as an executable (par2) along with the
required Intel Threading Building Blocks 4.3 Update 1 (libtbb.so and
libtbb.so.2). There are separate distributions for the 32-bit and
64-bit versions. They are also portable and can be run from a USB thumb
drive (no need to copy to the computer's internal storage device).

To install, place the par2, libtbb.so and libtbb.so.2 files in a
folder and invoke them from the command line.

To uninstall, delete the par2, libtbb.so and libtbb.so.2 files along
with any files from the distribution folder.


--- Building and installing on UNIX type systems ---


For UNIX or similar systems, the included configure script should be used to
generate a makefile which is then built with a Make utility. Before using
them however, you may need to modify the configure scripts as detailed below.

Because this version depends on the Intel Threading Building Blocks library,
you will need to tell the build system where the headers and libraries are in
order to compile and link the program. There are 2 ways to do this: use the
tbbvars.sh script included in TBB to add the appropriate environment variables,
or manually modify the Makefile to use the appropriate paths. The tbbvars.sh
file is in the tbb<version>oss_src/build directory. To manually modify the
Makefile:

  In `Makefile.am', for Darwin/Mac OS X, change the AM_CXXFLAGS line to:

AM_CXXFLAGS = -Wall -I../tbb43_20141023oss/include -gfull -O3 -fvisibility=hidden -fvisibility-inlines-hidden

  or for other POSIX systems, change the AM_CXXFLAGS line to:

AM_CXXFLAGS = -Wall -I../tbb43_20141023oss/include

and modify the path to wherever your extracted Intel TBB files are. Note that it
should point at the `include' directory inside the main tbb directory.

For linking, the file `Makefile.am' has this line:

LDADD = -lstdc++ -ltbb -L.

thus the tbb library is already added to the list of libraries to link against.
You will need to have libtbb.a (or libtbb.dylib or libtbb.so etc.) in your
library path (usually /usr/lib).

Alternatively, if the TBB library is not in a standard library directory (or
on the linker's list of library paths) then add a library path so the linker
can link to the TBB:

LDADD = -lstdc++ -ltbb -L<directory>

For example:

LDADD = -lstdc++ -ltbb -L.

The Mac OS X distribution of this project is built using a relative-path
for the dynamic library. Please see the next section for more information.

The GNU/Linux distribution of this project is built using a relative-path
for the dynamic library (by passing the "-R $ORIGIN" option to the linker).


--- Building and installing on Mac OS X systems ---


The Mac version is an universal build of the concurrent version of par2cmdline 0.4
for Mac OS X 10.5. In other words, the par2 executable file contains both a 32-bit
x86 and a 64-bit x86_64 build of the par2 sources.

It is distributed as an executable (par2) along with the required Intel
Threading Building Blocks 4.2 library (libtbb.dylib). The libtbb.dylib file
is also universal (32-bit and 64-bit versions for x86/x86_64 are inside it).

The distributed version is built on a 10.6.8 system using the compiler toolchain
from Xcode 3.2.6: GCC 4.2. The target OS is 10.5 using the 10.5 SDK.

The libtbb.dylib file in the distribution is built from the TBB 4.3 Update 1
tbb43_20141023oss_src.tgz sources, and was built for the x86 and x86_64
architectures.

The default compiler is clang 1.7 which does not compile the TBB library
(because it has bugs when compiling C++ source code), so it needs to changed
to GCC 4.2.

Normally, the libtbb.dylib file is built so that for a client program to use
it, it would have to be placed in /usr/lib, and would therefore require
administrator privileges to install it onto a Mac OS X system. The version
included in this distribution does not need to be installed in /usr/lib, and
is therefore usable "out of the box" and portable (eg, can be run from a USB
thumb drive).

So to build it the same way as in the distribution, the macos.clang.inc file
needs to be modified with these lines:

WARNING_SUPPRESS = -Wno-non-virtual-dtor ### -Wno-dangling-else (no-dangling-else is clang-specific)

LIB_LINK_FLAGS = -dynamiclib -Wl,-install_name,@executable_path/$@  ### enables portable .dylib

ifeq (intel64,$(arch))
    CPLUS = g++-4.2  ### because clang 1.7 cannot compile the TBB
    CPLUS_FLAGS += -m64 -mmacosx-version-min=10.5
    LINK_FLAGS += -m64 -mmacosx-version-min=10.5
    LIB_LINK_FLAGS += -m64 -mmacosx-version-min=10.5
endif

ifeq (ia32,$(arch))
    CPLUS = g++-4.2  ### because clang 1.7 cannot compile the TBB
    CPLUS_FLAGS += -m32 -mmacosx-version-min=10.5
    LINK_FLAGS += -m32 -mmacosx-version-min=10.5
    LIB_LINK_FLAGS += -m32 -mmacosx-version-min=10.5
endif

Then build the x86 and x86_64 variants using:

cd <TBB-src>
make tbb arch=ia32 SDKROOT=/Developer/SDKs/MacOSX10.5.sdk
make tbb arch=intel64 SDKROOT=/Developer/SDKs/MacOSX10.5.sdk

Then create the final dylib using (this example is built on a 10.6.8 system):

cp ./build/macos_ia32_clang_cc4.2.1_os10.6.8_release/libtbb.dylib libtbb-x86.dylib
cp ./build/macos_intel64_clang_cc4.2.1_os10.6.8_release/libtbb.dylib libtbb-x86_64.dylib
lipo -create -o libtbb.dylib libtbb-x86.dylib libtbb-x86_64.dylib 
strip -x libtbb.dylib 

To build the executables, configure needs to be invoked in a particular manner for both x86 and x64 builds:

cd <par2_tbb_root>/build
../configure --build=i686-apple-darwin10.2.0 --host=i686-apple-darwin10.2.0 CXX=g++-4.2 && sed -e 's/CXXFLAGS = -g -O2/CXXFLAGS = #-g -O2/' Makefile > Makefile.tmp && mv Makefile.tmp Makefile && make && strip par2 && mv par2 par2-x86 && make clean
../configure --build=i686-apple-darwin10.2.0 --host=x86_64-apple-darwin10.2.0 CXX=g++-4.2 && sed -e 's/CXXFLAGS = -g -O2/CXXFLAGS = #-g -O2/' Makefile > Makefile.tmp && mv Makefile.tmp Makefile && make && strip par2 && mv par2 par2-x86_64 && make clean
lipo -create -o par2 par2-x86 par2-x86_64

Note: the distributed copies of the par2 and libtbb.dylib files are symbol stripped (using the 'strip'
command line tool) to reduce their size.


--- Building and installing on Windows operating systems ---


This modified version has been built and tested on Windows 7 using Visual Studio 2013.
It statically links with both the TBB and the C runtime library and the included
Makefile, Project and Solution files are set up to build in this manner. To build the
program, you need to build the TBB as a static library and then build par2.

[1] install Windows SDK v7.1 (only the Windows headers and libraries are required)
    and Visual Studio 2013 for Windows Desktop or Visual Studio 2013 Community Edition
    (only the C++ compilers, headers and libraries are required).

[2] extract the TBB source tarball into a directory, which will be referred to as <tbb>
    in the instructions below

[3] in <tbb>/build, modify windows.inc:

# static library version of TBB does not need .def file:
#TBB.DEF = $(TBB.LST:.lst=.def)

# static library version of TBB should use .lib suffix:
#TBB.DLL = tbb$(CPF_SUFFIX)$(DEBUG_SUFFIX).$(DLL)
TBB.DLL = tbb$(CPF_SUFFIX)$(DEBUG_SUFFIX).$(LIBEXT)

# static library version of TBB does not need a version resource:
#TBB.RES = tbb_resource.res

# static library version of TBB uses lib.exe to build the library, not "cl.exe /DLL":
LIB_LINK_CMD = lib.exe

[4] in <tbb>/build, modify windows.cl.inc:

# static library version of TBB only needs to pass /nologo to lib.exe:
#LIB_LINK_FLAGS=/link /nologo /DLL /MAP /DEBUG /fixed:no /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
LIB_LINK_FLAGS=/nologo

# static library version of TBB cannot pass /SAFESEH to lib.exe:
#	LIB_LINK_FLAGS += /SAFESEH

# static library version of TBB asks lib.exe to output to tbb.lib or tbb_debug.lib:
#OUTPUT_KEY = /Fe
OUTPUT_KEY = /out:

[5] open Visual Studio 2013 -> Visual Studio Tools -> open a VS2013 x64 Cross Tools Command Prompt window

[6] modify these environment variables:

set INCLUDE=C:\Program Files (x86)\Microsoft SDKs\Windows\v7.1A\Include;C:\Program Files (x86)\Microsoft Visual Studio 12.0\VC\INCLUDE;
set LIB=C:\Program Files (x86)\Microsoft Visual Studio 12.0\VC\LIB\amd64;C:\Program Files (x86)\Microsoft SDKs\Windows\v7.1A\Lib\x64

[7] build a x64 (64-bit) version of the TBB using GNU make. If you do not have GNU make,
    first download the source tarball for it and build it using its instructions.

    Note the use of the vc_mt runtime, which asks to link the TBB library statically
	with the C runtime library:

cd <tbb>
gmake.exe tbb runtime=vc_mt arch=intel64

[8] open Visual Studio 2013 -> Visual Studio Tools -> open a VS2013 x86 Native Tools Command Prompt window

[9] modify these environment variables:

set INCLUDE=C:\Program Files (x86)\Microsoft SDKs\Windows\v7.1A\Include;C:\Program Files (x86)\Microsoft Visual Studio 12.0\VC\INCLUDE;
set LIB=C:\Program Files (x86)\Microsoft Visual Studio 12.0\VC\LIB;C:\Program Files (x86)\Microsoft SDKs\Windows\v7.1A\Lib

[10] build a x86 (32-bit) version of the TBB using GNU make:

cd <tbb>
gmake.exe tbb runtime=vc_mt arch=ia32

[11] from here, you can either build par2 using a Visual C++ project or from the command line using
     the Windows SDK make tool.

     To build using the Visual C++ project, open the par2cmdline.sln solution file in Visual Studio
     2013 for Windows Desktop (or the Community Edition), select the configuration you want to build,
     and then build the program.

     To build using the Windows SDK make tool, go back to the VS2013 x64 Cross Tools Command Prompt
     window you opened in step [5] and do this to create the par2_win64.exe executable:

cd <par2>
nmake nodebug=1 arch=x64
del *.obj

     Then go back to the VS2013 x86 Native Tools Tools Command Prompt window you opened in step [8]
     and do this to create the par2_win32.exe executable:

cd <par2>
nmake nodebug=1 arch=x86
del *.obj

    Note: the makefile assumes that the <par2> and <tbb> source folders are both in the same folder.
    If this is not the case, change this line in the Makefile so that the linker can find the TBB
    library you built above:


MY_TBB_DIR=../tbb43_20141023oss



--- Building and installing on FreeBSD ---


The instructions below are not needed if you use the FreeBSD ports system to
download, unpack, compile, link and install the program. Please see the
documentation in the ports system for instructions on its use. It is recommended
that the ports system be used to build the program since the source code can
build with modification. Please consider the following to be deprecated or for
educational use only.

Instructions for building without using the FreeBSD ports system:

[1] build and install TBB
- extract TBB from the source archive.
- on a command line, execute:

  cp -r <TBB-src>/include/tbb /usr/local/include
  cd <TBB-src> && /usr/local/bin/gmake
  # change the next line to match your machine's configuration:
  cp <TBB-src>/build/FreeBSD_em64t_gcc_cc4.1.0_kernel7.0_release/libtbb.so /usr/local/lib

[2] build and install par2cmdline-0.4-tbb
- extract and build par2cmdline-0.4-tbb using tar, ./configure, and make
- copy built binary to where you want to install it (eg, /usr/local/bin)

[3] cleanup
- remove <TBB-src> and par2cmdline-0.4-tbb source directories


--- Technical Details ---


All source code modifications have been isolated to blocks that have this form:

#if WANT_CONCURRENT

  <code added for concurrency>

#else

  <original code>

#endif

to make it easier to see what was modified and how it was done.

The technique used to modify the original code was:

[1] add timing code to instrument/document the places where concurrency would be of
    benefit. The CTimeInterval class was used to time sections of the code.
[2] decide which functions to make concurrent, based on the timing information
    obtained in step [1].
[3] for each function to make concurrent, study it and its sub-functions for
    concurrent access problems (shared data points)
[4] read the Intel TBB tutorials and reference manual to learn how to use the
    library to convert serial code to concurrent code

It was then decided to apply concurrency to:

- loading of recovery packets (par2 files), which necessitated changes to some member
  variables in par2repairer.h:
  - sourcefilemap [LoadDescriptionPacket, LoadVerificationPacket]
  - recoverypacketmap [LoadRecoveryPacket]
  - mainpacket [LoadMainPacket]
  - creatorpacket [LoadCreatorPacket]
  They were changed to use concurrent-safe containers/wrappers. To handle concurrent
  access to pointer-based member variables, the pointers are wrapped in atomic<T>
  wrappers. tbb::atomic<T> does not have operator-> which is needed to deference
  the wrapped pointers so a sub-class of tbb::atomic<T> was created, named
  atomic_ptr<T>. For maps and vectors, tbb's concurrent_hash_map and concurrent_vector
  were used.
  Because DiskFileMap needed to be accessed concurrently, a concurrent version of it
  was created (class ConcurrentDiskFileMap)
- source file verification
- repairing data blocks

In the original version, progress information was written to cout (stdout) in a serial
manner, but the concurrent version would produce garbled overlapping output unless
output was made concurrent-safe. This was achieved in two ways: for simple infrequent
output routines, a simple mutex was used to gate access to cout to only one thread at
a time. For frequent use of cout, such as during the repair process, an atomic integer
variable was used to gate access, but *without* blocking a thread that would have
otherwise been blocked if a mutex had been used instead. The code used is:

  if (0 == cout_in_use.compare_and_swap(outputendindex, 0)) { // <= this version doesn't block - only need 1 thread to write to cout
    cout << "Processing: " << newfraction/10 << '.' << newfraction%10 << "%\r" << flush;
    cout_in_use = 0;
  }

Initially cout_in_use is set to zero so that the first thread to put its value of
outputendindex into cout_in_use will get a zero back from cout_in_use.compare_and_swap()
and therefore enter the 'true block' of the 'if' statement. Other threads that then try
to put their value of outputendindex into cout_in_use while the first thread is still
using cout will fail to do so and so they will skip the 'true block' but they won't block.

For par2 creation, similar modifications were made to the source code that also allowed
concurrent processing to occur.

To convert from serial to concurrent operation, for() loops were changed to using Intel
TBB parallel_for() calls, with a functor object (callback) supplied to provide the body
of the parallel for loop. To access member variable in the body of the parallel loop,
new member functions were added so that the functor's operator() could dispatch into the
original object to do the for loop body's processing.

It should be noted that there are two notable parts of the program that could not be
made concurrent: (1) file verification involves computing MD5 hashes for the entire file
but computing the hash is an inherently serial computation, and (2) computing the Reed-
Solomon matrix for use in creation or repair involves matrix multiplication over a Galois
field, which is also an inherently serial computation and so it too could not be made into
a concurrent operation.

Nevertheless, the majority of the program's execution time is spent either repairing the
lost data, or in creating the redundancy information for later repair, and both of these
operations were able to be made concurrent with a near twice speedup on the dual core
machines that the concurrent version was tested on.

Note that it is important that the computer has sufficient memory (1) to allow the caching
of data and (2) to avoid virtual memory swapping, otherwise the creation or repair process
will become I/O bound instead of CPU bound. Computers with 1 to 2GB of RAM should have
enough memory to not be I/O bound when creating or repairing parity/data files.


--- Version History ---


The changes in the 20141125 version are:

- when creating parity files, the main packet was not always being written to the parity
  files when they were processed concurrently because the main packet was not being
  safely appended to the list of packets to output because a non-thread-safe data
  container (std::list<T>) was being used. This bug would manifest when a large number
  of source files were being processed. Fixed by using tbb::concurrent_vector<T> instead
  of std::list<T>.
- when creating parity files, the "Opening: <file>" messages will only be displayed for
  the first n source files, where n defaults to 200. This restriction was added so that
  creating parity files for a large number of source files would not cause a lot of
  scrolling which in turn would make the processing take a long time. Use the new -z<n>
  command line switch to set a different limit. Use -z0 to specify no limit.
- verification of extra files is now performed concurrently if requested to do so
  (previously they were always verified serially)
- the -t parameter can now include a positive integer value to restrict the logical number
  of CPUs with which to process data with. The different variants are:
  -t- verifies, repairs, and creates serially (no change)
  -t+ verifies, repairs, and creates concurrently (no change)
  -t0 verifies serially and repairs/creates concurrently (no change)
  -t-n verifies, repairs, and creates concurrently using the maximum number of logical
       CPUs minus n, or 1 (whichever is larger) for n > 0; n <= 0 is illegal
  -t+n verifies, repairs, and creates concurrently using the maximum number of logical
       CPUs, or n (whichever is smaller) for n > 0; n <= 0 is illegal
  -t0n verifies serially and repairs/creates concurrently using:
      for n > 0: the maximum number of logical CPUs, or n (whichever is smaller)
      for n < 0: the maximum number of logical CPUs minus n, or 1 (whichever is larger)
      for n = 0: illegal
  For example, -t-1 on a 6 logical CPU system will use up to 5 logical CPUs. On the
  same system, -t-7 will use up to 1 logical CPU, ie, process serially.
  - "up to" is used because there may not be enough data to use the maximum number of
    logical CPUs.
  - the maximum number of logical CPUs may be determined by the operating system or the
    hypervisor and may be less than the actual number of physical CPU cores, eg, when
	running in a virtual machine.
- in the Windows version, the program's CPU scheduling priority can now be specified
  using the -p parameter:
  -pN to process at normal priority (Normal in Task Manager) [default]
  -pL to process at low priority (Below Normal in Task Manager)
  -pI to process at idle priority (Low in Task Manager)
- the heap became fragmented during the verification of data files because the checksum
  data buffer was allocated and deallocated for each file verified, which resulted in the
  program's memory footprint (aka its "working set") steadily increasing during the
  verification phase. This would result in the 32-bit Windows version failing to verify
  large data sets because it could not allocate verification data buffers. To solve this,
  the checksum data buffer is no longer allocated and deallocated for each file verified.
  Instead, a pool of checksum objects is created and that pool of objects is then used and
  re-used for verifying data files. The size of the pool matches the number of logical
  CPUs which the program is asked to use. This change benefits all versions of the program
  because by reducing heap fragmentation, larger data sets can be processed using less
  virtual memory.
- numerous small code changes were made to remove unnecessary string copying. Such
  redundant copying would further fragment the heap as well as use up memory for temporary
  strings which did not need to be allocated in the first place.
- updated to Intel TBB 4.3 Update 1 (tbb43_20141023oss_src.tgz)
- removed use of MAX_PATH or other fixed-size path buffers to avoid buffer overflow errors
- the program failed to build under newer C++ standard libraries because they no longer
  provide std::auto_ptr<T>. Fixed by either using std::unique_ptr<T> (if available) or by
  providing our own version of std::auto_ptr<T>.
- the Mac OS x86 (32-bit) version now requires 10.5 or later
- stopped building the FreeBSD version because the FreeBSD ports system can now build the
  par2 program and TBB library without requiring any changes to the sources of either and
  because it isn't possible to build a "portable" version of the program, in the sense
  that the TBB library cannot be in the same directory as the par2 executable - it must be
  installed into /usr/lib/, and that is a job best left to the FreeBSD ports system.

The changes in the 20100203 version are:

- modified Makefile.am to use "ARCH_SCALAR" instead of "ARCH" to avoid a FreeBSD name clash
- fixed a 64-bit-only bug in reedsolomon-x86_64-mmx.s where a size of 8 bytes caused a segfault
(forgot to test for zero like the reedsolomon-i686-mmx.s file does); this bug only manifests in
the 64-bit Mac, 64-bit Linux and 64-bit FreeBSD versions; reproduced by creating/repairing a
file of exactly 16384 bytes
- updated to Intel TBB 2.2 (tbb22_20090809oss)
- the Mac build no longer includes the PowerPC variants (I don't use a PowerPC Mac anymore)
- the 32-bit and 64-bit Windows builds of both par2 and the TBB library are now statically
linked against the C runtime library to avoid the problem of requiring the installation of
the correct CRT library (DLL). As well, par2 is statically linked against the TBB library
to allow just one executable file to be installed (i.e., just par2.exe).

The changes in the 20090203 version are:

- fixed a bug which affected the Linux and Mac versions whereby repairs would fail if
the file being repaired was short or had one or two bad blocks (because the async write
to the file's last byte was failing).
- on Windows, the program now stores directory paths in par2 files using '/' as the path
separator instead of '\' (as per the Par 2.0 specification document). Note: directory
paths are stored only when the '-d' switch is used.
- merged the sources from the CPU-only and CPU/GPU versions so that both versions now
build from the same set of source files using different 'configure' options (Mac, Linux,
FreeBSD) or project files (Windows). See above for building instructions.

The changes in the 20081009 version are:

- added support for NVIDIA CUDA 2.0 technology, which allows the GPU on the video card to
  be used to perform some of the processing workload in addition to the CPU on the mainboard.
  See the "--- About the NVIDIA CUDA version ---" section in this file for limitations,
  requirements, build instructions, licensing, and more information.

The changes in the 20081005 version are:

- asynchronous reading of a large number of small files would sometimes not complete which
  caused the program to hang. Fixed by reverting to synchronous reading (most of the benefit
  of async I/O is from async writing so this change does not affect overall performance).
- some operating systems have limits on the number of open files which was easily exceeded
  when a large number of small files are being processed for par2 creation or for repair.
  Fixed by closing the source files as soon as they are no longer needed to be opened (which
  is determined by counting how many data blocks the file provides for creation/repair).

The changes in the 20080919 version are:

- added more information to a few of the error messages to make it easier to specify
  block counts, etc. when using the -d option.
- redundancy can now be specified using floating point values instead of integral values,
  eg, 8.5% instead of 8% or 9%.
- added the -0 option to create dummy par2 files. This was done so that the actual size
  of the par2 files can be quickly determined. For example, suppose you wish to fill up
  a CD-R's or DVD-R's remaining empty space with par2 files of the files filling up the
  disc, then by using the -0 option, you can quickly work out whether the par2 files
  will fit and by how much, which in turn allows you to maximize the use of the remaining
  empty space (you would alter the block count number and/or size so that the optimal
  number of blocks are created to fill up the remaining space). To determine how much
  CD-R or DVD-R space you have to fill, find out how many blocks your blank disc has
  (using a burning program such as ImgBurn [Windows]) and how many blocks your data
  would occupy when burned (using an image creation program such as mkisofs [all
  platforms] which has a handy -print-size option). ImgBurn [Windows] can also tell
  you how many blocks you have for filling if you use its 'build' command.
  WARNING: be careful when using this command that you don't burn the dummy par2 files
  that it creates because they don't have any valid data in them. Remember, they are
  created only to determine the actual size of the real par2 files that would be
  created if you had not used the -0 option.
- added MMX-based code from Paul Houle's phpar2_12src version of par2cmdline-0.4. As
  a result, the repair and creation of par2 files using x86 or x86_64 MMX code is about
  20% faster than the scalar version in singlethreaded testing. Multithreaded testing
  showed no noticable improvement (ie, YMMV). The scalar version is used if your CPU
  is not MMX capable. MMX CPUs: Intel Pentium II and later, AMD Athlon64 and later.
- added asynchronous I/O for platforms that support such I/O: Mac OS X, Windows,
  GNU/Linux. This results in a small (~1-5%) improvement in throughput, especially for
  repairing. Unfortunately, using async I/O causes a crash under FreeBSD, so the
  pre-built binaries are built to only use synchronous I/O.
- first release of 32-bit and 64-bit PowerPC binaries for Mac OS X. The 32-bit version
  requires at least 10.4, and the 64-bit version requires at least 10.5. The 64-bit
  version is UNTESTED (because of lack of access to a G5 Mac).
- first release of a 64-bit x86_64 binary for GNU/Linux. Tested under the 64-bit
  version of Gentoo 2008.0.
- the 64-bit Windows binary is built using the tbb20_20080408oss release of the TBB;
  the Mac, GNU/Linux, FreeBSD and 32-bit Windows binaries are built using the
  tbb21_009oss release of the TBB. The tbb21_009oss release does not support the
  VC7.1 runtime libraries on Win64 so it was necessary to fallback to a previous
  version for the Windows 64-bit binary.

The changes in the 20080420 version are:

- added the -t0 option to allow verification to be done serially but still perform
  repair concurrently, and for creation, MD5 checksumming will be done serially
  and par2 data creation will be done concurrently. The default is to perform
  all operations concurrently, so if you want the new behaviour, you will need to
  manually specify -t0 on the command line or build your own custom version of
  the executable.
- if the realpath() API returned NULL, the par2 files created would end up with
  the name of the first file in the list of files to create par2 files for. Fixed.
- no longer includes duplicate file names in the list of files to create redundancy
  data for (which would otherwise bloat the .par2 files)
- now displays the instruction set being executed
- updated to use the tbb20_017oss_src.tar.gz version of the Intel TBB library.

The changes in the 20080203 version are:

- the Linux version wasn't working because it was not built correctly: the
  reedsolomon-inner-i386-posix.s was using an incorrect include directive. Fixed.
  *** WARNING ***
  A consequence of this error is that par2 files created with the 20080116 Linux
  binary contain incorrect repair data and therefore cannot be used to repair
  data files. The par2 files will need to be created again using either the
  20071128 build of the Linux binary or this build of it.
  *** WARNING ***
- tweaked the Makefile and par2cmdline.h to allow for building under FreeBSD.
- first release of 32-bit and 64-bit binaries for FreeBSD (built under RELEASE 6.2).
- updated to use the 20080115 version of the Intel TBB library.

The changes in the 20080116 version are:

- the initial processing (creation) and verification (repair) of target files
  is now performed serially because of complaints that concurrent processing
  was causing disk thrashing. Since this part of the program's operation is
  mostly I/O bound, the change back to serial processing is a reasonable change.
- full paths are now only displayed when a -d parameter is given to the
  program, otherwise the original behavior of displaying just the file name
  now occurs.
- Unicode support was added. This requires some explanation.

  Windows version: previous versions processed file names and directory
  paths using the default code page for non-Unicode programs, which is
  typically whatever the current locale setting is. In other words,
  file names that had characters that could not be represented in the
  default code page ended up being mangled by the program, resulting
  in .par2 files which contained mangled file names (directory names
  also suffered mangling). Such .par2 files could not be used on other
  computers unless they also used the same code page, which for POSIX
  systems is very unlikely. The correct solution is to store and retrieve
  all file names and directory paths using a Unicode representation.
  To keep some backward compatibility, the names should be stored in
  an 8-bit-per-character format (so that older .par2 files can still
  be processed by the program), so decomposed (a.k.a. composite) UTF-8
  was chosen as the canonical file name encoding for the storage of
  file names and directory paths in .par2 files.
  To implement this change, the Windows version now takes all file
  names from the operating system as precomposed UTF-16 and converts
  them to decomposed UTF-8 strings which are stored in memory and
  in .par2 files. If the operating system needs to use the string,
  it is converted back into precomposed UTF-16 and then passed to
  the OS for use.

  POSIX version: it is assumed that the operating system will deliver
  and accept decomposed (a.k.a. composite) UTF-8 characters to/from
  the program so no conversion is performed. Darwin / Mac OS X is
  one such system that passes and accepts UTF-8 character strings, so
  the Mac OS X version of the program works correctly with .par2
  files containing Unicode file names. If the operating system
  does not deliver nor accept decomposed UTF-8 character strings,
  this version (and previous versions) will not create .par2 files
  that contain Unicode file names or directory paths, and which
  will cause mangled file/directory names when used on other
  operating systems.

  Summary:
  [1] for .par2 files created on Windows using a version of
  this program prior to this version and which contain non-ASCII
  characters (characters outside the range of 0 - 127 (0x00 - 0x7F)
  in numeric value, this program will be able to use such files
  but will probably complain about missing files or will create
  repaired files using the wrong file name or directory path, ie,
  file name mangling will occur.
  [2] for .par2 files created on UTF-8 based operating systems
  using a prior version of this program, this version will be
  able to correctly use such files (ie, the changes made to the
  program should not cause any change in behavior, and no file
  name mangling will occur).
  [3] for .par2 files created on non-UTF-8 based operating systems
  using a prior version of this program, this version will be
  able to use such files but file name mangling will occur.
  [4] for .par2 files created on UTF-8 based operating systems
  using this version of this program, file name mangling will
  not occur.
  [5] for .par2 files created on non-UTF-8 based operating systems
  using this version of this program, file name mangling will
  occur.

- split up the reedsolomon-inner.s file so that it builds
  correctly under Darwin and other POSIX systems.
- changed the way the pre-built Mac OS X version is built because
  the 64-bit version built under 10.4 (1) crashes when it is run
  under 10.5, and (2) does not read par2 files when the files
  reside on a SMB server (ie, a shared folder on a Windows
  computer) because 10.4's SMB client software appears to
  incorrectly service 64-bit client programs. These problems only
  occurred with the 64-bit version; the 32-bit version works
  correctly.

  To solve both of these problems, the pre-built executable is now
  released containing both a 32-bit executable built under 10.4
  and a 64-bit executable built under 10.5. When run under 10.4,
  the 64-bit executable does not execute because it is linked
  against the 10.5 system libraries, so under 10.4, only the
  32-bit executable is executed, which solves problem (2). When
  run under 10.5 on a 64-bit x86 computer, the 64-bit executable
  executes, which solves problem (1), and because 10.5's SMB
  client correctly services 64-bit client programs, problem (2)
  is solved.

The changes in the 20071128 version are:

- if par2 was asked to verify/repair with just a single .par2 file, it would
  crash. Fixed.
- built for GNU/Linux using the Gentoo distribution (i386 version).
- updated to use the 20071030 version of the Intel TBB library.

The changes in the 20071121 version are:

- changed several concurrent loops from using TBB's parallel_for to
  parallel_while so that files will be processed in a sequential (but
  still concurrent/threaded) manner. For example, 100 files were
  previously processed on dual core machines as:
  Thread 1: file 1, file 2, file 3, ..., file 50
  Thread 2: file 50, file 51, file 52, ..., file 100
  which caused hard disk head thrashing. Now the threads will
  process the files from file 1 to file 100 on a
  first-come-first-served basis.
- limited the rate at which cout was called to at most 10 times per
  second.
- when building for i386 using GCC, this version will now build
  with an assembler version of the inner Reed-Solomon loop because
  the code generated by GCC was not as fast/small as the Visual
  C++ version. Doing this should bring the GCC-built (POSIX)
  version's speed up to that of the Visual C++ (Windows) version.
- for canonicalising paths on POSIX systems, the program will now
  try to use the realpath() API, if it's available, instead of the
  fragile code in the original version.
- on POSIX systems, attempting to use a parameter of "-d." for par2
  creation would cause the program to fail because it was not
  resolving a partial path to a canonical full path. Fixed.

The changes in the 20071022 version are:

- synchronised the sources with the version of par2cmdline in the CVS at <http://sourceforge.net/projects/parchive>
- built against the 20070927 version of the Intel TBB
- tweaked the inner loop of the Reed Solomon code so that the compiler
  will produce faster/better/smaller code (which may or may not speed up
  the program).
- added support for creating and repairing data files in directory trees
  via the new -d<directory> command line switch.

  The original modifications for this were done by Pacer:

<http://www.quickpar.co.uk/forum/viewtopic.php4?t=460&amp;start=0&amp;postdays=0&amp;postorder=asc&amp;highlight=&amp>

  This version defaults to the original behaviour of par2cmdline: if no
  -d switch is provided then the data files are expected to be in the same
  directory that the .par2 files are in.

  Providing a -d switch will change the way that par2cmdline behaves as follows.
  For par2 creation, any file inside the provided <directory> will have
  its sub-path stored in the par2 files. For par2 repair, files for
  verification/repair will be searched for inside the provided <directory>.

  Example:

    in /users/home/vincent/pictures/ there is
       2007_01_vacation_fiji
         01.jpg
         02.jpg
         03.jpg
         04.jpg
       2007_03_business_trip_usa
         01.jpg
         02.jpg
       2007_06_wedding
         01.jpg
         02.jpg
         03.jpg
         04.jpg
         05.jpg
         06.jpg

    Using the command:

./par2 c -d/users/home/vincent/pictures/ /users/home/vincent/pictures.par2 /users/home/vincent/pictures

    will create par2 files in /users/home/vincent containing sub-paths such as:

      2007_01_vacation_fiji/01.jpg
      2007_01_vacation_fiji/02.jpg
      2007_01_vacation_fiji/03.jpg
      2007_01_vacation_fiji/04.jpg
      2007_03_business_trip_usa/01.jpg
      2007_03_business_trip_usa/02.jpg
      2007_06_wedding/01.jpg
      etc. etc.

    If you later try to repair the files which are now in /users/home/joe/pictures,
    you would use the command:

      ./par2 r -d/users/home/joe/pictures/ /users/home/joe/pictures.par2

    The par2 file could be anywhere on your disk: as long as the -d<directory>
    switch specifies the root of the files, the verification/repair will occur correctly.

    Notes:

    [1] the directory given to -d does not need to have a trailing '/' character.
    [2] on Windows, either / or \ can be used.
    [3] partial paths can be used. For example, if the current directory is
        /users/home/vincent, then this be used instead of the above command:

        ./par2 c -dpictures pictures.par2 pictures

    [4] if a directory has spaces or other characters that need escaping from the
        shell then the use of double quotes is recommended. For example:

        ./par2 c "-dpicture collection" "picture collection.par2" "picture collection"


The changes in the 20070927 version are:

- applied a fix for a bug reported by user 'shenhanc' in 
Par2CreatorSourceFile.cpp where a loop variable would not get
incremented when silent output was requested.

The changes in the 20070926 version are:

- fixed an integer overflow bug in Par2CreatorSourceFile.cpp which resulted
in incorrect MD5 hashes being stored in par2 files when they were created
from source files that were larger than or equal to 4GB in size. This bug
affected all 32-bit builds of the program. It did not affect the 64-bit
builds on those platforms where sizeof(size_t) == 8.

The changes in the 20070924 version are:

- the original par2cmdline-0.4 sources were not able to process files
larger than 2GB on the Win32 platform because diskfile.cpp used the
stat() function which only returns a signed 32-bit number on Win32.
This was changed to use _stati64() which returns a proper 64-bit file
size. Note that the FAT32 file system from the Windows 95 era does not
support files larger than 1 GB so this change is really applicable only
to files on NTFS disks - the default file system on Windows 2000/XP/Vista.

The changes in the 20070831 version are:

- modified to utilise Intel TBB 2.0.



Vincent Tan.
November 25, 2014.
<chuchusoft@gmail.com>

//
//  Modifications for concurrent processing, Unicode support, and hierarchial
//  directory support are Copyright (c) 2007-2014 Vincent Tan.
//  Search for "#if WANT_CONCURRENT" for concurrent code.
//  Concurrent processing utilises Intel Thread Building Blocks 4.3 Update 1,
//  Copyright (c) 2007-2014 Intel Corp.
//
