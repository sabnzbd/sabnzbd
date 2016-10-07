par2cmdline is a PAR 2.0 compatible file verification and repair tool.

To see the ongoing development see
https://github.com/BlackIkeEagle/par2cmdline

The original development was done on Sourceforge but stalled.
For more information from the original authors see
http://parchive.sourceforge.net
Also for details of the PAR 2.0 specification and discussion of all 
things PAR.

WHAT EXACTLY IS PAR2CMDLINE?

par2cmdline is a program for creating and using PAR2 files to detect
damage in data files and repair them if necessary. It can be used with
any kind of file.

WHY IS PAR 2.0 better than PAR 1.0?

 * It is not necessary to split a single large file into many equally
   size small files (although you can still do so if you wish).

 * There is no loss of efficiency when operating on multiple files
   of different sizes.

 * It is possible to repair damaged files (using exactly the amount of
   recovery data that corresponds to the amount of damage), rather than
   requiring the complete reconstruction of the damaged file.

 * Recovery files may be of different sizes making it possible to
   obtain exactly the amount of recovery data required to carry out
   a repair.

 * Because damaged data files are still useable during the recovery
   process, less recovery data is required to achieve a successful
   repair. It is therefore not necessary to create as much recovery
   data in the first place to achieve the same level of protection.

 * You can protect up to 32768 files rather than the 256 that PAR 1.0
   is limited to.

 * Damaged or incomplete recovery files can also be used during the
   recovery process in the same way that damaged data files can.

 * PAR 2.0 requires less recovery data to provide the same level of 
   protection from damage compared with PAR 1.0.

DOES PAR 2.0 HAVE ANY DISADVANTAGES?

Yes, there is one disadvantage:

 * All PAR 2.0 program will take somewhat longer to create recovery
   files than a PAR 1.0 program does.

This disadvantage is considerably mitigated by the fact that you don't
need to create as much recovery data in the first place to provide the
same level of protection against loss and damage.

COMPILING PAR2CMDLINE

You should have received par2cmdline in the form of source code which
you can compile on your computer. You may optionally have received a
precompiled version of the program for your operating system.

If you have only downloaded a precompiled executable, then the source
code should be available from the same location where you downloaded the
executable from.

If you have MS Visual Studio .NET, then just open the par2cmdline.sln
file and compile. You should then copy par2cmdline.exe to an appropriate
location that is on your path.

To compile on Linux and other Unix variants use the following commands:

  aclocal
  automake --add-missing
  autoconf
  ./configure
  make
  make check
  make install

See INSTALL for full details on how to use the "configure" script.

USING PAR2CMDLINE

The command line parameters for par2cmdline are as follow:

    par2 -h  : show this help
    par2 -V  : show version
    par2 -VV : show version and copyright

    par2 c(reate) [options] <par2 file> [files]
    par2 v(erify) [options] <par2 file> [files]
    par2 r(epair) [options] <par2 file> [files]

  Also:

    par2create [options] <par2 file> [files]
    par2verify [options] <par2 file> [files]
    par2repair [options] <par2 file> [files]

  Options:

    -a<file> : Set the main par2 archive name
               required on create, optional for verify and repair
    -b<n>    : Set the Block-Count
    -s<n>    : Set the Block-Size (Don't use both -b and -s)
    -r<n>    : Level of Redundancy (%)
    -r<c><n> : Redundancy target size, <c>=g(iga),m(ega),k(ilo) bytes
    -c<n>    : Recovery block count (don't use both -r and -c)
    -f<n>    : First Recovery-Block-Number
    -u       : Uniform recovery file sizes
    -l       : Limit size of recovery files (Don't use both -u and -l)
    -n<n>    : Number of recovery files (Don't use both -n and -l)
    -m<n>    : Memory (in MB) to use
    -v [-v]  : Be more verbose
    -q [-q]  : Be more quiet (-qq gives silence)
    -p       : Purge backup files and par files on successful recovery or
               when no recovery is needed
    -R       : Recurse into subdirectories (only useful on create)
    -N       : No data skipping (find badly misspositioned data blocks)
    -S<n>    : Skip leaway (distance +/- from expected block position)
    --       : Treat all remaining CommandLine as filenames

If you wish to create par2 files for a single source file, you may leave
out the name of the par2 file from the command line. par2cmdline will then
assume that you wish to base the filenames for the par2 files on the name
of the source file.

You may also leave off the .par2 file extension when verifying and repairing.

CREATING PAR2 FILES

With PAR 2.0 you can create PAR2 recovery files for as few as 1 or as many as
32768 files. If you wanted to create PAR1 recovery files for a single file
you were forced to split the file into muliple parts and RAR was frequently
used for this purpose. You do NOT need to split files with PAR 2.0.

To create PAR 2 recovery files for a single data file (e.g. one called
test.mpg), you can use the following command:

  par2 create test.mpg.par2 test.mpg

If test.mpg is an 800 MB file, then this will create a total of 8 PAR2 files
with the following filenames (taking roughly 6 minutes on a PC with a
1500MHz CPU):

  test.mpg.par2          - This is an index file for verification only
  test.mpg.vol00+01.par2 - Recovery file with 1 recovery block
  test.mpg.vol01+02.par2 - Recovery file with 2 recovery blocks
  test.mpg.vol03+04.par2 - Recovery file with 4 recovery blocks
  test.mpg.vol07+08.par2 - Recovery file with 8 recovery blocks
  test.mpg.vol15+16.par2 - Recovery file with 16 recovery blocks
  test.mpg.vol31+32.par2 - Recovery file with 32 recovery blocks
  test.mpg.vol63+37.par2 - Recovery file with 37 recovery blocks

The test.mpg.par2 file is 39 KB in size and the other files vary in size from
443 KB to 15 MB.

These par2 files will enable the recovery of up to 100 errors totalling 40 MB
of lost or damaged data from the original test.mpg file when it and the par2
files are posted on UseNet.

When posting on UseNet it is recommended that you use the "-s" option to set
a blocksize that is equal to the Article size that you will use to post the
data file. If you wanted to post the test.mpg file using an article size
of 300 KB then the command you would type is:

  par2 create -s307200 test.mpg.par2 test.mpg

This will create 9 PAR2 files instead of 8, and they will be capable of
correcting up to 134 errors totalling 40 MB. It will take roughly 8 minutes
to create the recovery files this time.

In both of these two examples, the total quantity of recovery data created
was 40 MB (which is 5% of 800 MB). If you wish to create a greater or lesser
quantity of recovery data, you can use the "-r" option.

To create 10% recovery data instead of the default of 5% and also to use a
block size of 300 KB, you would use the following command:

  par2 create -s307200 -r10 test.mpg.par2 test.mpg

This would also create 9 PAR2 files, but they would be able to correct up to
269 errors totalling 80 MB. Since twice as much recovery data is created, it
will take about 16 minutes to do so with a 1500MHz CPU.

The "-u" and "-n" options can be used to control exactly how many recovery
files are created and how the recovery blocks are distributed among them.
They do not affect the total quantity of recovery data created.

The "-f" option is used when you create additional recovery data e.g. If 
you have already created 10% and want another 5% then you migh use the 
following command:

  par2 create -s307200 -r5 -f300 test.mpg.par2 test.mpg

This specifies the same block size (which is a requirement for additional
recovery files), 5% recovery data, and a first block number of 300.

The "-m" option controls how much memory par2cmdline uses. It defaults to
16 MB unless you override it.

When creating PAR2 recovery files you might want to fill up a "medium" like a
DVD or a Blu-Ray. Therefore we can set the target size of the recovery files by
issuing the following command:

  par2 create -rm200 recovery.par2 *

It makes no sense to set a insanely high recovery size. The command will make
that the resulting sum of the par2 files approaches the requested size. It is
an estimate so don't go to crazy.

CREATING PAR2 FILES FOR MULTIPLE DATA FILES

When creating PAR2 recovery files from multiple data files, you must specify
the base filename to use for the par2 files and the names of all of the data
files.

If test.mpg had been split into multiple RAR files, then you could use:

  par2 create test.mpg.rar.par2 test.mpg.part*.rar

The files filename "test.mpg.rar.par2" says what you want the par2 files to
be called and "test.mpg.part*.rar" should select all of the RAR files.

VERIFYING AND REPAIRING

When using par2 recovery files to verify or repair the data files from
which they were created, you only need to specify the filename of one
of the par2 files to par2cmdline.

e.g.:

  par2 verify test.mpg.par2

This tells par2cmdline to use the information in test.mpg.par2 to verify the
data files.

par2cmdline will automatically search for the other par2 files that were
created and use the information they contain to determine the filenames
of the original data files and then to verify them.

If all of the data files are OK, then par2cmdline will report that repair
will not be required.

If any of the data files are missing or damaged, par2cmdline will report
the details of what it has found. If the recovery files contain enough
recovery blocks to repair the damage, you will be told that repair is
possible. Otherwise you will be told exactly how many recovery blocks
will be required in order to repair.

To carry out a repair use the following command:

  par2 repair test.mpg.par2

This tells par2cmdline to verify and if possible repair any damaged or
missing files. If a repair is carried out, then each file which is
repaired will be re-verified to confirm that the repair was successful.

MISNAMED AND INCOMPLETE DATA FILES

If any of the recovery files or data files have the wrong filename, then
par2cmdline will not automatically find and scan them.

To have par2cmdline scan such files, you must include them on the command
line when attempting to verify or repair.

e.g.:

  par2 r test.mpg.par2 other.mpg

This tells par2cmdline to scan the file called other.mpg to see if it
contains any data belonging to the original data files.

If one of the extra files specified in this way is an exact match
for a data file, then the repair process will rename the file so that
it has the correct filename.

Because par2cmdline is designed to be able to find good data within a
damaged file, it can do the same with incomplete files downloaded from
UseNet. If some of the articles for a file are missing, you should still
download the file and save it to disk for par2cmdline to scan. If you
do this then you may find that you can carry out a repair in a situation
where you would not otherwise have sufficient recovery data.

You can have par2cmdline scan all files that are in the current directory
using a command such as:

  par2 r test.mpg.par2 *

WHAT TO DO WHEN YOU ARE TOLD YOU NEED MORE RECOVERY BLOCKS

If par2cmdline determines that any of the data files are damaged or
missing and finds that there is insufficient recovery data to effect
a repair, you will be told that you need a certain number of recovery
blocks. You can obtain these by downloading additional recovery files.

In order to make things easy, par2 files have filenames that tell you
exactly how many recovery blocks each one contains.

Assuming that the following command was used to create recovery data:

  par2 c -b1000 -r5 test.mpg

Then the recovery files that are created would be called:

  test.mpg.par2
  test.mpg.vol00+01.par2
  test.mpg.vol01+02.par2
  test.mpg.vol03+04.par2
  test.mpg.vol07+08.par2
  test.mpg.vol15+16.par2
  test.mpg.vol31+19.par2

The first file in this list does not contain any recovery data, it only
contains information to verify the data files.

Each of the other files contains a different number of recovery blocks.
The number after the '+' sign is the number of recovery blocks and the
number preceding the '+' sign is the block number of the first recovery
block in that file.

If par2cmdline told you that you needed 10 recovery blocks, then you would
need "test.mpg.vol01+02.par2" and "test.mpg.vol07+08.par". You might of course
choose to fetch "test.mpg.vol15+16.par2" instead (in which case you would have
an extra 6 recovery blocks which would not be used for the repair).

REED SOLOMON CODING

PAR2 uses Reed Solomon Coding to perform its calculations. For details of this
coding technique try the following link:

``A Tutorial on Reed-Solomon Coding for Fault-Tolerance in RAID-like Systems''
<http://web.eecs.utk.edu/~plank/plank/papers/CS-96-332.html>
