# lzxdec

Source of `core/fsmod/bin/lzxdec.exe`, the LZX decoder `fsmod.chunk` runs to read `chunklzx` entries of the
game's `.big` archives.

- `lzxd.c`, `lzx.h`, `mspack.h`, `system.c`, `system.h`, `readbits.h`, `readhuff.h`, `macros.h`: unchanged files of
  [libmspack](https://www.cabextract.org.uk/libmspack/) by Stuart Caie, licensed under the
  GNU Lesser General Public License (LGPL) version 2.1 ([COPYING.LIB](COPYING.LIB)).
- `lzxdec.c`: small command-line wrapper around `lzxd_decompress`
  (`lzxdec <raw lzx input> <output> <window_bits> <output size>`).

Build (Windows, with `pip install ziglang`), from this folder:

```bat
python -m ziglang cc -target x86_64-windows-gnu -mcpu=baseline -O2 -o ..\fsmod\bin\lzxdec.exe lzxdec.c lzxd.c -I.
del ..\fsmod\bin\lzxdec.pdb
```

Always keep `-target` and `-mcpu=baseline`: without them zig builds for the CPU of the machine that compiles
(`native`), and the exe may use instructions other processors lack (an exe built on a CPU with AVX-512 ended with
`0xC000001D`, illegal instruction, on an Intel 12th gen). Baseline x86-64 runs on any 64-bit PC.
