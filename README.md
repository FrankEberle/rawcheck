# RAWCHECK

Simple Python script to check integrity of RAW images files.
Integrity check is performed by converting the RAW file using
the [dcraw_emu](https://www.libraw.org/docs/Samples-LibRaw.html)
binary of [LibRaw](https://www.libraw.org).
The script crawls over the specified directory and invokes
muliple instances of *dcraw_emu* to make use of multiple CPU cores.
