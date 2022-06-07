# Creating `par2` for M1 systems

Compiled on an M1 system using these steps.

If you do not use llvm and `clang++` it will not include multithreading support.

However, I was unable to statically link the `libomp` library inside the `par2` executable.
I extracted it from the llvm libs folder and modified `par2` to look for the `libomp.dylib` in the same folder using `install_name_tool`.

Ref: https://stackoverflow.com/questions/4677044/how-to-use-dylib-in-mac-os-x-c

```shell
brew install automake
brew install llvm
echo 'export PATH="/opt/homebrew/opt/llvm/bin:$PATH"' >> ~/.zshrc

# Restart terminal and clone/download par2cmdline sources

./automake.sh
CPPFLAGS="-I/opt/homebrew/opt/llvm/include" LDFLAGS="-L/opt/homebrew/opt/llvm/lib" CXX="clang++" ./configure
make clean
make
make check

# Do magic to copy and modify the OpenMP library
cp /opt/homebrew/opt/llvm/lib/libomp.dylib .
install_name_tool -change /opt/homebrew/opt/llvm/lib/libomp.dylib @executable_path/libomp.dylib ./par2
```
