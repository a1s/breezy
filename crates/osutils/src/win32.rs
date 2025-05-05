use bitflags::bitflags;
use std::fs::Metadata;
use std::os::windows::fs::MetadataExt;
use winapi::um::winnt::{FILE_ATTRIBUTE_DIRECTORY, FILE_ATTRIBUTE_READONLY};

bitflags! {
    #[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
    pub struct SFlag: u32 {
        const S_IFIFO = 0x1000;
        const S_IFCHR = 0x2000;
        const S_IFDIR = 0x4000;
        const S_IFBLK = 0x6000;
        const S_IFREG = 0x8000;
        const S_IFLNK = 0xA000;
        const S_IFSOCK = 0xC000;
        const S_IFMT = 0xF000;
    }
}

impl SFlag {
    pub fn from_metadata(metadata: &Metadata) -> Self {
        let attr = metadata.file_attributes();
        // From Python2 posixmodule.c
        let mut mm: u32 = 0;
        if (attr & FILE_ATTRIBUTE_DIRECTORY) > 0 {
            mm |= SFlag::S_IFDIR.bits() | 0111; // Execute permissions
        } else {
            mm |= SFlag::S_IFREG.bits();
        };
        if (attr & FILE_ATTRIBUTE_READONLY) > 0 {
            mm |= 0444;
        } else {
            mm |= 0666;
        };
        Self::from_bits_retain(mm)
    }
}
