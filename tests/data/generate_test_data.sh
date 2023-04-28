#!/bin/sh

# Generate data sets for test_functional_downloads

FILENAME="My_Test_Download.bin" # a non-obfuscated filename: capitals and spaces

fallocate -l100k $FILENAME
rar a basic_rar5/testfile  $FILENAME

rm test_zip/*
zip test_zip/testfile.zip $FILENAME

rm test_7zip/*
7z a test_7zip/testfile.7z $FILENAME
rar a -psecret test_passworded\{\{secret\}\}/passworded-file $FILENAME
rm $FILENAME

FILENAME100k="My_Test_Download.bin"
cd obfuscated_single_rar_set
rm *
fallocate -l100k $FILENAME100k
rar a postfile  -v15k -m0  $FILENAME100k
for FILE in *rar ; do mv $FILE `uuidgen` ; done
rm $FILENAME100k
cd ..


UNICODE_FILENAME="我喜欢编程_My_Test_Download.bin"
cd unicode_rar
rm *
fallocate -l100k $UNICODE_FILENAME
rar a 我喜欢编程  -v20k -m0 $UNICODE_FILENAME
par2 create -r10 -n7 我喜欢编程  *rar
rm $UNICODE_FILENAME
cd ..




