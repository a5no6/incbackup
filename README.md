# incbackup.py  Incremental backup script

Backup incrementaly without overwrintg previously backuped data, and restore any backuped file.  
Can define excluding pattern for each directory  
Check hash of files and does not backup files just time has been updated, renamed or moved.  
Tested on Windows 10(python 3.6), ubuntu18/20   

## Requirement
    python3  
    7z  
    sox (linux only)  

## How to backup.
    1. prepare configuration file (default name is backup_config.txt, ex. F:\dst_folder\backup_config.txt)  
    2. run this program with python   
        windows : python incbackup.py backup F:\backup  
        linux   : python incbackup.py backup /media/yourname/usbdisk/backup  
    3. You can find backup data in dst_folder(ex F:\backup)\archive\YYYYMMDDNN in 7z arhive files.  
       And you can restore data by  
         python incbackup.py restore F:\backup  

## Configuration file (UTF-8)
    Default configuration file is backup_config.txt in top directory of destination folder  
    Lines start with # are ignored as comment  
    In 1st line, specify top directory of backup source. (ex. C:\Users\youraccount\Documents)  
    In 2nd line, specify extensions not want to compress any more. (ex. jpg,zip )  
    Starting with 3rd line, specify backup folders and exclude rules separated by comma.   
      For example   
        work,\*.obj,\*.pch,\*.log  
        means backup C:\Users\uarname\Documents\work recursively, except for files of which name matches *.obj ,*.pch or *.log  
        Pattern strings like \*.obj are passed to python re.match command. Please read python document for details.    

### configuration file example for windows (DRIVEPATH:\dst_folder\backup_config.txt)
    # reference folder of backup (only 1 path)
    C:/Users/youraccount/
    # file extensions, not to compress
    jpg,jpeg,tif,tiff,mp3,pdf,mp4,avi,7z,zip,lzh
    ### backup location (multiple lines) pathname,reject_pattern1,reject_pattern2,...
    ###  .+  means Do not enter the folder
    bin/,__pycache__
    kicad/
    MPLABXProjects/,/release$,/debug$,/build$,/dist$,.git$,.log$
    work/
    work/octave,.mat$
    work/blender,.+
    esp/idf,/build$,/.metadata$,TAGS
    eclipse-workspace/,/build$,/.metadata$
    Documents/
    Desktop/

### configuration file example for linux (/media/youraccount/somemedia/dst_folder/backup_config.txt)
    # reference folder of backup (only 1 path)
    /home/youraccount/
    # file extensions, not to compress
    jpg,jpeg,tif,tiff,mp3,pdf,mp4,avi,7z,zip,lzh
    ### backup location (multiple lines) pathname,reject_pattern1,reject_pattern2,...
    ###  .+  means Do not enter the folder
    bin/,__pycache__
    kicad/

## Command examples
### backup
    Backup files to F:\backup according to F:\backup\backup_config.txt
        python incbackup.py backup F:\backup
    Backup files to F:\backup according to /somewhere/some_config.txt
        python incbackup.py backup F:\backup -c /somewhere/some_config.txt
    Make index only (If you've made full backup to larger device and  want incbackup to backup updated files only, please initialize with this method.)
        python incbackup.py empty F:\backup


### restore
    Restore latest data to current directory.  
        python incbackup.py restore F:\backup"   
    Restore data of specific time  
        python incbackup.py restore  F:\backup -t YYYY/MM/DD-HH:MM:SS  
    Restore specific data of specific time  
        python incbackup.py restore  F:\backup -t YYYY/MM/DD-HH:MM:SS -f pathname/filename  
    Restore all versions of backuped data for some file.  
        python incbackup.py history  F:\backup -f pathname/filename  
### common options
    Set password to backupdata  
        python incbackup.py backup F:\backup -p yourpassword
    Do not beep 
        python incbackup.py backup F:\backup --silent
    Pause 5 seconds before exiting program
        python incbackup.py backup F:\backup -w 5  

## Flash drive consideration
  USB flash drive is a typical backup device. But flash drive has a shorter life time of about a couple of thousands writes.
  If you backup just small data less than a clustor (ex. 32k bytes ), a sector in FAT will be written 3 times in worst case (directory,fileinfo.txt,7zip file ).
  In case of FAT32, each cluster consists of 4 bytes and a sector consists of 512 bytes, so same FAT sector might be written 512/4=128 times before moving to next FAT sector.
  I recommend you choose small cluster size for a flash drive format if you will backup small amount of data many times.

