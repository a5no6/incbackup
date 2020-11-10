#!/usr/bin/python
"""
MIT License

Copyright (c) 2020 Konomu Abe

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

#backup_config.txt example.
# reference folder of backup (only 1 path)
C:/Users/youraccount/
# file extensions, not to compress
jpg,jpeg,tif,tiff,mp3,pdf,mp4,avi,7z,zip,lzh,7z
# backup location (multiple lines) pathname,exclude_pattern1,exclude_pattern2,...
#  .+  means Do not enter the folder
Desktop/
Documents/,\.~lock\.\w+\.ods#$
Documents/Visual Studio 2012/Projects/,\.obj$,\.pch$,\.ipch$,\.sdf,tlog$,\.idb$,\.pdb$
Documents/Visual Studio 2015/Projects/,\.obj$,\.pch$,\.ipch$,\.VC,tlog$,\.idb$,\.pdb$,\.ilk$
Documents/My Pictures/,.+
Documents/My Music/,.+
Documents/My Videos/,.+
# File name is also allowed
Video/some.mp4
Pictures/,\.RW2$
"""
import sys
import os
import logging
import hashlib
import datetime
import subprocess
import re
import time
import shutil
import traceback
import stat
import argparse

if os.name == 'posix' : # assume ubuntu
    SEVEN_ZIP = "7z"
else:
    SEVEN_ZIP = "C:/Program Files/7-Zip/7z.exe"
    import winsound

class backup_config_struct:
    def __init__(self):
        self.password = False
        self.mode = None
        self.recovery_files = []
        self.RECOVERY_TIME = -1
        self.NOCOMPRESS_EXTNSION = []
        self.ARCHIVE_FILE_COMPRESS = "/comp_arch.7z"
        self.ARCHIVE_FILE_NOCOMPRESS = "/nocomp_arch.7z"
        self.ARCHIVE_FILE_EXT = ".001"
        self.ARCHIVE_FILE_INFO_NAME = "fileinfo.txt"
        self.PRINT_MAX_FILE_NUM = 100
        self.DO_BEEP = True
        self.OVERWRITE_OPT = []
        self.EXTRACT_METHOD = "x"    
        self.DEFAULT_CONFIG_FILE_NAME = "backup_config.txt"
        self.ARCHIVE_FOLDER_NAME = "archive/"
        self.RESTORE_LIST_FILE = "arhive_list.txt"
        self.DELETE_ON_FAIL = False  ## delete not perfect arhive when arhiver failed.
        self.WAIT_SEC_BEFORE_EXIT = 0
        if os.name == 'posix' : # assume ubuntu
            self.WORKDIR = "/tmp/incbackuptemp/"
        else:
            self.WORKDIR = "C:/tmp/incbackuptemp/"
        self.MOVE_TEMP = self.WORKDIR + "extract_temp/"

    def read_config_files(self,conf_file_list):
        tree_top = {}
        for conf_file in conf_file_list:
            f = open(conf_file,encoding="utf8")
            lines = f.read().split("\n")
            f.close()
            while "" in lines:
                lines.remove("")
            stripped_lines = []
            for l in lines:
                if not l[0] == "#":
                    stripped_lines.append(l)
            src = stripped_lines[0]
            if src[-1] not in ["/","\\"]:
                src += "/"
            nocompress = stripped_lines[1].split(",")
            while "" in nocompress:
                nocompress.remove("")
            ext_low = []
            for l in nocompress:
                ext_low.append(l.lower())
            for l in stripped_lines[2:]:
                c = l.split(",")
                mask_pattern = c[1:]
                while "" in mask_pattern:
                    mask_pattern.remove("")
                path = backslash_to_slash(c[0])
                if path[-1] == "/":
                    path = path[:-1]
                tree_top[path] = mask_pattern
                logger.debug("%s:%s"%(path,tree_top[path]))
        self.NOCOMPRESS_EXTNSION = ext_low
        self.src_top = src
        self.dst_top = tree_top
    
    def get_backup_temp_filename_comp(self,n):
        return(self.WORKDIR+"bc_%s.txt"%n)
    
    def get_backup_temp_filename_nocomp(self,n):
        return(self.WORKDIR+"bn_%s.txt"%n)

    def get_restore_temp_filename_comp(self,n):
        return(self.WORKDIR+"rc_%s.txt"%n)
    
    def get_restore_temp_filename_nocomp(self,n):
        return(self.WORKDIR+"rn_%s.txt"%n)

class backuped_files_struct:
    def __init__(self):
        self.file_sha = {}
        self.file_mtime = {}
        self.file_archive_num = {}
        self.file_org_path = {}
        self.file_is_compressed = {}
        self.archive_time = {}

    def get_fileinfo_data(self,archive_folder,info_file_name,n):
        folder = archive_folder + n
        if stat.S_ISDIR(os.stat(folder).st_mode):
            path = archive_folder + n + "/" + info_file_name
            f = open(path,encoding="utf8")
            lines = f.read()
            f.close()
        else:
            print("%s is not a directory"%folder)
            raise FileNotFoundError
        lines = lines.split('\n')
        return(lines)

    def reconstruct_incremental(self,archive_folder,info_file_name):
        self.file_mtime = {}
        self.file_sha = {}
        self.file_archive_num = {}
        self.file_org_path = {}
        self.file_is_compressed = {}
        num = sorted(list(self.archive_time.keys()))
        logger.debug("backup to reconstruct%s"%num)
        for n in num:
            lines = self.get_fileinfo_data(archive_folder,info_file_name,n)
            for l in lines[1:]: ## skip 1st line (comment line)
                c = split_including_commma(l)
                if len(c)<5:
                    continue
                oldpath = get_proper_pathname(c[0])
                newpath = get_proper_pathname(c[1])
    
                if len(oldpath)>0 and len(newpath)>0 and oldpath!=newpath: # move
                    self.file_mtime[newpath] = str2time(c[2])
                    self.file_sha[newpath] = self.file_sha[oldpath]
                    self.file_archive_num[newpath] = self.file_archive_num[oldpath]
                    self.file_is_compressed[newpath] = self.file_is_compressed[oldpath]
                    if self.file_org_path[oldpath] == False:
                        self.file_org_path[newpath] = oldpath
                    else:
                        self.file_org_path[newpath] = self.file_org_path[oldpath]
    
                    if newpath == self.file_org_path[newpath]: # come back to the original location
                        self.file_org_path[newpath] = False
    
                elif len(newpath) > 0: # new path exist,then add
                    self.file_mtime[newpath] = str2time(c[2])
                    self.file_sha[newpath] = bytes.fromhex(c[4])
                    self.file_archive_num[newpath] = n
                    self.file_is_compressed[newpath] = (c[3]=="C" or c[3]=="c")
                    self.file_org_path[newpath] = False
    
                if (len(oldpath) > 0 and oldpath!= newpath) : # old path exist,then remove
                    self.file_mtime.pop(oldpath)
                    self.file_sha.pop(oldpath)
                    self.file_archive_num.pop(oldpath)
                    self.file_is_compressed.pop(oldpath)
                    self.file_org_path.pop(oldpath)
    
def feedbackbeep(is_success):
    if not backup_config.DO_BEEP:
        return
    else:
        if is_success:
            try:
                if os.name == 'posix' : # assume ubuntu
                    os.system('play -nq -t alsa synth 0.1 sine 110')
                else:
                    winsound.Beep(400,300)
            except:
                pass
        else :
            for beepcount in range(3):
                try:
                    if os.name == 'posix' : # assume ubuntu
                        os.system('play -nq -t alsa synth 1 sine 110')
                    else:
                        winsound.Beep(400,1000)
                    time.sleep(0.3)
                except:
                    pass
        

def time2str(t):
    return(time.strftime("%Y/%m/%d-%H:%M:%S",time.localtime(t)))

def str2time(s):
    return(time.mktime(time.strptime(s,"%Y/%m/%d-%H:%M:%S")))

def delete_temporary_file(file):
    os.remove(file)
    
def create_path(full_path):
    if "\\" in full_path:
        path_sym = "\\"
    else:
        path_sym = "/"
    each_path = full_path.split(path_sym)
    path = ""
    for s in each_path[:-1]:
        path = path + s +path_sym
        if not os.path.isdir(path):
            os.mkdir(path)

def strip_double_quote(s):
    if len(s)>2 and s[0]=='"':
        if s[-1]=='"':
            return(s[1:-1])
        else:
            logging.error("double quote does not match %s"%s)
            return(s)
    else:
        return(s)

def add_double_quote(s):
    if s[0]=='"':
        return(s)
    else:
        return('"'+s+'"')

def strip_path(s):
    fname = s.split('/')[-1]
    if fname[-1]=='"':
        return('"'+fname)
    else:
        return(fname)

def backslash_to_slash(s):
    return(re.sub("\\\\","/",s))

def split_including_commma(l):
    #concat path name if path name include ',' 20170929 added
    c_org = l.split(",")
    if len(c_org)<5:
        return([])
    c = []
    for filenames in range(2):
        c.append(c_org.pop(0))
        while True:
            if len(c[-1])==0:  # No file name 
                break
            if c[-1][-1] == '"':
                break
            c[-1] += ','
            c[-1] += c_org.pop(0)
    c += c_org
    return(c)

def get_proper_pathname(s):
    # Internally 
    #    use / (not \) 
    #    remove ""
    #    do not add / for directory 
    if s=="":
        return(s)
    p = backslash_to_slash(strip_double_quote(s))
    while p[-1]=="/":
        p = p[:-1]
    return(p)
    
def create_backup_file_obj(archive_folder,recovery_time):
    backup_exec = {}
    folders = os.listdir(archive_folder)
    for f in folders:
        match = re.search("^(\d{10,10})$",f)
        if match:
            logger.debug(f)
            t = os.stat(archive_folder+f).st_mtime 
            if recovery_time<0 or t <= recovery_time:
                backup_exec[f] = t
    created_data = backuped_files_struct()
    created_data.archive_time = backup_exec
    return(created_data)

def find_files(folder,reject_pattern_list):
    mtime = {}
    try:
        if len(folder)>0:
            files = os.scandir(folder,)
        else:
            files = os.scandir(".")
    except PermissionError:
        logger.warning("Permission error for listdir %s"%folder)
        return(mtime)
#    for f1 in files:
    for entry in files:
        f1 = entry.name
        if len(folder)>0 and not (folder[-1]=='/' or folder[-1]=='\\'): 
            f = folder+'/'+f1
        else:
            f = folder+f1
        flag = False
        for ptn in reject_pattern_list:
            mt =  re.search(ptn,f)
            if mt:
                flag = True
                break
        if flag:
            continue
#        if os.path.isdir(f) and ((f in BACKUP_STOP_FOLDER)or(f+'/' in BACKUP_STOP_FOLDER)):
        if entry.is_dir(follow_symlinks=False) and ((f in backup_config.BACKUP_STOP_FOLDER)or(f+'/' in backup_config.BACKUP_STOP_FOLDER)):
            continue
#        if os.path.isdir(f) :
        if entry.is_dir(follow_symlinks=False) :
            _mtime = find_files(f,reject_pattern_list)
            for _m in _mtime.keys():
                mtime[_m] = _mtime[_m]
        else:
            if os.path.islink(f):
                continue
            try:
                mtime[f] = entry.stat(follow_symlinks=False).st_mtime
            except PermissionError:
                logger.warning("Permission error %s"%f)
    return(mtime)

def search_target_file_and_get_mtime(_backup_top):
    mtimes = {}
    print("Searching target")
    for backup_folder in _backup_top.keys():
        logger.debug("%s:%s"%(backup_folder,_backup_top[backup_folder]))
        if _backup_top[backup_folder] == []:
            is_folder = os.path.isdir(backup_folder) # isdir does not raise error without folder or file.
        else:
            is_folder = True
        if is_folder:
            mtime = find_files(backup_folder,_backup_top[backup_folder])
            print(" %d files in %s"%(len(mtime),backup_folder))
            for m in mtime:  ##### better method ?
                mtimes[m] = mtime[m]
        else:
            try:
                mtimes[backup_folder] = os.stat(backup_folder).st_mtime
            except FileNotFoundError:
                logger.warning("FileNotFoundError %s"%backup_folder)
            except PermissionError:
                logger.warning("Permission error %s"%backup_folder)
    return(mtimes)

calc_hash_count = 0
def calc_hash(path):
    global calc_hash_count
##    try:
    m = hashlib.sha256()
    dispdot = int((1024*1024/2048/ m.block_size)) * 16 # MBytes
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(2048 * m.block_size), b''):
            m.update(chunk)
            calc_hash_count += 1
            if calc_hash_count >= dispdot:
                calc_hash_count -= dispdot
                sys.stdout.write(".")
                sys.stdout.flush()
    return(m.digest())

def find_difference(p_mtime,p_sha,new_mtime):
    add_sha = {}
    add_list = []
    update_list = []
    delete_list = []
    move_list = []
    for path in new_mtime.keys():
        if path in p_mtime.keys():
            if p_mtime[path] - new_mtime[path] > 2 or p_mtime[path] - new_mtime[path] < -1:
                update_list.append(path)
        else:
            add_list.append(path)
    print("Calculating hash for adding %d files"%len(add_list))
    for p in add_list:
        try:
            add_sha[p] = calc_hash(p)
        except PermissionError:
            add_list.remove(p)
    print("done")
    for path in p_mtime.keys():
        if path not in new_mtime.keys():
            delete_list.append(path)
    delete_list2 = delete_list.copy()
    for src_path in delete_list2:
        src_sha = p_sha[src_path]
        dst_sha_key = list(add_sha.keys())
        dst_sha_val = list(add_sha.values())
        if src_sha in dst_sha_val:
            dst_path = dst_sha_key[dst_sha_val.index(p_sha[src_path])]
            move_list.append([src_path,dst_path])
            delete_list.remove(src_path)
            add_sha.pop(dst_path)
            logger.debug("moved file %s -> %s"%(src_path,dst_path))
    return(add_sha,update_list,delete_list,move_list)

def compress_char(path):
    if is_file_to_compress(path):
        type_char = "C"
    else:
        type_char = "N"
    return(type_char)

def make_archive_info_file(fname,mtime_dict,add_sha,update_list,delete_list,move_list):
    print("Making file list to backup.")
    f = open(fname,"wt",encoding="utf8")
    f.write("### previous path(blank if new),new path(blank if delete),last modified,C=compress/N=non compress,sha value\n")
    for p in add_sha.keys():
        f.write(',"%s",%s,%s,%s\n'%(p,time2str(mtime_dict[p]),compress_char(p),bytes.hex(add_sha[p]).upper()))
    print("Calculating hash for updated %d files"%len(update_list))
    for p in update_list:
        try:
            h = bytes.hex(calc_hash(p)).upper()
            f.write('"%s","%s",%s,%s,%s\n'%(p,p,time2str(mtime_dict[p]),compress_char(p),h))
        except PermissionError:
            logger.warning("Permission denied for %s"%p)
    
    print("done.")
    for p in delete_list:
        f.write('"%s",,-1,%s,00\n'%(p,compress_char(p)))
    for p in move_list:
        try:
            h = bytes.hex(calc_hash(p[1])).upper()
            f.write('"%s","%s",%s,%s,%s\n'%(p[0],p[1],time2str(mtime_dict[p[1]]),compress_char(p[0]),h))
        except PermissionError:
            logger.warning("Permission denied for %s"%p[1])
    f.close()

def make_backup_date_number(past_bk):
    today = datetime.date.today().strftime("%Y%m%d")
    for d in range(100):
        bkname = today + "%02d"%d
        if bkname not in past_bk.keys():
            return(bkname)

def is_file_to_compress(pathname):
    ext = pathname.split(".")[-1].lower()
    if ext[-1]=='"':
        ext = ext[0:-1]            
    if ext in backup_config.NOCOMPRESS_EXTNSION:
        return(False)
    else:
        return(True)    

def make_archive_list_for_7z(fname,nocomp_ext,compress_file,nocomp_file):
    f = open(fname,encoding="utf8")
    lines = f.read().split("\n")
    f.close()
    fnocomp = open(nocomp_file,"wt",encoding="utf8")
    fcomp = open(compress_file,"wt",encoding="utf8")
    nocomp = 0
    comp = 0
    for l in lines:
        c = l.split(",")
        if not len(c) == 5:
            continue
        prev_name = c[0]
        pathname = c[1]
        if (pathname == "") or ((not prev_name=="") and (not prev_name==pathname)):  # delete or move
            continue
        if is_file_to_compress(pathname):
            fcomp.write("%s\n"%pathname)
            comp+=1
        else:
            fnocomp.write("%s\n"%pathname)
            nocomp += 1
    fnocomp.close()
    fcomp.close()
    return(comp,nocomp)

def verify():
    prev_dir = os.getcwd()
    os.chdir(backup_config.src_top)
    print("Entered %s"%backup_config.src_top)
    latest_backup_time = backuped_files.archive_time[sorted(backuped_files.archive_time.keys())[-1]]
    current_mtime = search_target_file_and_get_mtime(backup_config.dst_top)
    current_files = list(current_mtime.keys())
    missing_files = []  # found in backup, but not in the current files
    for f in backuped_files.file_sha.keys():
        try :
            if backuped_files.file_sha[f] != calc_hash(f):
                print("\nWrong hash %s:%s %s"%(f,bytes.hex(backuped_files.file_sha[f]),bytes.hex(calc_hash(f))))
            current_files.remove(f)
#        except FileNotFoundError:
        except ValueError:
            missing_files.append(f)
    print("")
    if len(current_files)>0:
        untracked_files = []
        unknown_files = []
        for f in current_files:
            if os.stat(f).st_ctime> latest_backup_time:
                untracked_files.append(f)
            else:
                unknown_files.append(f)
        if len(untracked_files)>0:
            print("%d untracked files added after the last backup"%len(untracked_files))
            print("")
        if len(unknown_files)>0:
            print("unknown(exist only in current files) files")
            for f in unknown_files:
                print("  %s"%f)
            print("")
    if len(missing_files)>0:
        print("missing(exist only in backup files) %d files."%len(missing_files))
        for f in missing_files:
            print("  %s"%f)
        print("")
    
    if len(missing_files)==0 and len(current_files)==0:
        print("All %d files were checked."%(len(backuped_files.file_sha)))
        print("")
    os.chdir(prev_dir)

def backup(mode):
    backup_start_time = time.time()
    prev_dir = os.getcwd()
    os.chdir(backup_config.src_top)
    current_mtime = search_target_file_and_get_mtime(backup_config.dst_top)
    print("Scan disk %.2f sec"%(time.time()-backup_start_time))
    backup_number = make_backup_date_number(backuped_files.archive_time)

    # append , update , delete , modify
    a,u,d,m = find_difference(backuped_files.file_mtime,backuped_files.file_sha,current_mtime)

    if len(a)> 0 or len(d)>0 or len(m)>0 or len(u)>0:
        try:
            logging.info("create " + backup_config.ARCHIVE_FOLDER + backup_number)
            os.mkdir(backup_config.ARCHIVE_FOLDER + backup_number)
        except FileExistsError:
            pass
        make_archive_info_file(backup_config.ARCHIVE_FOLDER + backup_number +"/"+backup_config.ARCHIVE_FILE_INFO_NAME,current_mtime,a,u,d,m)
        opt_7zip = []
        arhive_sucess = True
        if backup_config.password:
            opt_7zip.append(backup_config.password)
        if mode=='backup':
            msg = ""
            compress_file_name = backup_config.get_backup_temp_filename_comp(backup_number)
            nocompress_file_name = backup_config.get_backup_temp_filename_nocomp(backup_number)
            n_compress,n_nocom = make_archive_list_for_7z(backup_config.ARCHIVE_FOLDER + backup_number +"/"+backup_config.ARCHIVE_FILE_INFO_NAME,backup_config.NOCOMPRESS_EXTNSION,compress_file_name,nocompress_file_name)
            if n_compress>0:
                print("compressing %d files"%n_compress)
                try:
                    reply = subprocess.check_output([SEVEN_ZIP,"a", backup_config.ARCHIVE_FOLDER + backup_number +backup_config.ARCHIVE_FILE_COMPRESS,"-mx1","-v1g","@%s"%compress_file_name]+opt_7zip)
                    msg += reply.decode()
                except subprocess.CalledProcessError:
                    print("Error occured while arhive")
                    arhive_sucess = False
                except UnicodeDecodeError:
                    print("UnicodeDecodeError occured in 7z message")
                    try:
                        print(reply)
                    except:
                        pass
            if n_nocom > 0:
                print("archiving %d files"%n_nocom)
                try:
                    reply += subprocess.check_output([SEVEN_ZIP,"a",backup_config.ARCHIVE_FOLDER + backup_number +backup_config.ARCHIVE_FILE_NOCOMPRESS,"-mx0","-v1g","@%s"%nocompress_file_name]+opt_7zip)
                    msg += reply.decode()
                except subprocess.CalledProcessError:
                    print("Error occured while arhive")
                    arhive_sucess = False
                except UnicodeDecodeError:
                    print("UnicodeDecodeError occured in 7z message")
                    try:
                        print(reply)
                    except:
                        pass
            logger.debug(msg)
            delete_temporary_file(compress_file_name)
            delete_temporary_file(nocompress_file_name)
        print("##############################################")
        if (backup_config.DELETE_ON_FAIL == True) and (arhive_sucess == False):
            shutil.rmtree(backup_config.ARCHIVE_FOLDER + backup_number)
            print("Backup failed.!!!!!!!!!!!!!!!!!!!!!!!!!")
            feedbackbeep(False)
        else:
            if len(a) > 0:
                print("added")
                if len(a) > backup_config.PRINT_MAX_FILE_NUM:
                    print("  %d files"%len(a))
                else:
                    for f in a.keys():
                        print("  "+f)
            if len(u) > 0:
                print("updated")
                if len(u) > backup_config.PRINT_MAX_FILE_NUM:
                    print("  %d files"%len(u))
                else:
                    for f in u:
                        print("  "+f)
            if len(d) > 0:
                print("deleted")
                if len(d) > backup_config.PRINT_MAX_FILE_NUM:
                    print("  %d files"%len(d))
                else:
                    for f in d:
                        print("  "+f)
            if len(m) > 0:
                print("moved")
                if len(m) > backup_config.PRINT_MAX_FILE_NUM:
                    print("  %d files"%len(m))
                else:
                    for f in m:
                        print("  "+f[0]+"->"+f[1])
        print("##############################################")
    else:
        print("\n\nNothing to backup.")
    os.chdir(prev_dir)

def restore(mode):
    recovery_files = backup_config.recovery_files.copy()
    opt_7zip = []
    if backup_config.password:
        opt_7zip.append(backup_config.password)

    if mode=="restore":
        try:
            logging.info("create " + backup_config.MOVE_TEMP)
            os.mkdir(backup_config.MOVE_TEMP)
        except FileExistsError:
            pass
    if mode=="list":
        flist = open(backup_config.RESTORE_LIST_FILE,"wt",encoding="utf8")
        flist.write("## path,backup_number,C=compressed/N=nocompressed,last_modified\n")
        print("Making list only.\n%s"%backup_config.RESTORE_LIST_FILE)

    print("Current directory is %s"%os.getcwd())
    if input("Restore/list continue OK? (Enter y) ").lower() != "y":
        return

    for n in sorted(list(backuped_files.archive_time.keys())):
        files_compress = []
        files_nocompress = []
        files_compress_move = []
        files_nocompress_move = []
        for p in backuped_files.file_mtime:
            if backuped_files.file_archive_num[p] == n:
                if len(recovery_files)==0 or p in recovery_files:
                    if backuped_files.file_org_path[p] == False:
                        if backuped_files.file_is_compressed[p]:
                            files_compress.append(p)
                        else:
                            files_nocompress.append(p)
                    else:
                        if backuped_files.file_is_compressed[p]:
                            files_compress_move.append(p)
                        else:
                            files_nocompress_move.append(p)
        if mode=="restore": 
            compress_file_name = backup_config.get_restore_temp_filename_comp(n)
            nocompress_file_name = backup_config.get_restore_temp_filename_nocomp(n)
            for is_file_moved in [False,True]:
                for extrace_files, extract_list_name,archive_name in zip(
                    ([files_compress_move,files_nocompress_move]if is_file_moved==True else [files_compress,files_nocompress]) ,
                            [compress_file_name,nocompress_file_name], [backup_config.ARCHIVE_FILE_COMPRESS,backup_config.ARCHIVE_FILE_NOCOMPRESS]):
##                    print(extrace_files)
                    if len(extrace_files)>0:
##                        print(extract_list_name)
                        f = open(extract_list_name,"wt",encoding="utf8")
                        for p in extrace_files:
                            if is_file_moved:
                                f.write('"%s"\n'%backuped_files.file_org_path[p])
                            else:
                                f.write('"%s"\n'%p)
                        f.close()
                        archive_file = backup_config.ARCHIVE_FOLDER + n + archive_name + backup_config.ARCHIVE_FILE_EXT
                        try:
                            os.stat(archive_file)
                            try:
#                                print(os.listdir())
                                seven_zip_cmd = [SEVEN_ZIP,backup_config.EXTRACT_METHOD, archive_file,"@%s"%extract_list_name] + backup_config.OVERWRITE_OPT + opt_7zip
                                print(archive_file)
                                if is_file_moved:
                                    seven_zip_cmd.append("-o"+backup_config.MOVE_TEMP)                                
                                msg = subprocess.check_output(seven_zip_cmd).decode()
                                logger.info(msg)
                                if is_file_moved:
                                    for p in extrace_files:
                                        try:
                                            create_path(p)
                                            shutil.move(backup_config.MOVE_TEMP+ backuped_files.file_org_path[p],p) ####
                                            print("shutil.mov %s,%s"%(backup_config.MOVE_TEMP+backuped_files.file_org_path[p],p))
                                        except FileNotFoundError:
                                            print("FileNotFoundError in moving %s->%s"%(backuped_files.file_org_path[p],p))
                                delete_temporary_file(extract_list_name)
                            except subprocess.CalledProcessError:
                                print("7z error in %s.\nMay be same file exsit."%(archive_file))                                
                        except FileNotFoundError:
                            print(" not found." + archive_file + " skip.")
        elif mode=="list":
            for p in files_compress:
                flist.write("%s,%s,C,%s\n"%(p,n,time2str(backuped_files.file_mtime[p])))
            for p in files_nocompress:
                flist.write("%s,%s,N,%s\n"%(p,n,time2str(backuped_files.file_mtime[p])))
            for p in files_compress_move:
                flist.write("%s,%s,C,%s\n <-%s\n"%(p,n,time2str(backuped_files.file_mtime[p]),backuped_files.file_org_path[p]))
            for p in files_nocompress_move:
                flist.write("%s,%s,N,%s\n <-%s\n"%(p,n,time2str(backuped_files.file_mtime[p]),backuped_files.file_org_path[p]))
    if mode=="restore":
        unmoved_files = find_files(backup_config.MOVE_TEMP,[])
        if len(unmoved_files) > 0:
            logger.error("Unmoved files exist %s"%unmoved_files)
        else:
            shutil.rmtree(backup_config.MOVE_TEMP)
    if mode=="list":
        flist.close()

def history():
    recovery_files = backup_config.recovery_files.copy()
    opt_7zip = []
    if backup_config.password:
        opt_7zip.append(backup_config.password)

    try:
        logging.info("create " + backup_config.MOVE_TEMP)
        os.mkdir(backup_config.MOVE_TEMP)
    except FileExistsError:
        pass

    print("Current directory is %s"%os.getcwd())
    if input("Make history continue OK? (Enter y) ").lower() != "y":
        return

    for p in recovery_files:
        create_path(strip_double_quote(p)+"/dummy")

    for n in sorted(list(backuped_files.archive_time.keys())):
        f = open(backup_config.ARCHIVE_FOLDER+n+"/"+backup_config.ARCHIVE_FILE_INFO_NAME ,encoding="utf8")
        lines = f.read().split('\n')
        f.close()
        for l in lines[1:]: ## skip 1st line (comment line)
            c = split_including_commma(l)
            if len(c)<5:
                continue

            if strip_double_quote(c[1]) in recovery_files:
                if c[0] != "" and c[0]!=c[1]:  # move 
                    continue

                recover_file_name = strip_double_quote(c[1])
                if c[3]=="C":
                    archive_file = backup_config.ARCHIVE_FOLDER + n + backup_config.ARCHIVE_FILE_COMPRESS + backup_config.ARCHIVE_FILE_EXT
                else:
                    archive_file = backup_config.ARCHIVE_FOLDER + n + backup_config.ARCHIVE_FILE_NOCOMPRESS + backup_config.ARCHIVE_FILE_EXT
                try:
                    os.stat(archive_file)
                except FileNotFoundError:
                    continue

                seven_zip_cmd = [SEVEN_ZIP,"e", archive_file] + backup_config.OVERWRITE_OPT + opt_7zip + [recover_file_name]

                msg = subprocess.check_output(seven_zip_cmd).decode()
                logger.debug(msg)
                dst = recover_file_name + '/%s'%n
                shutil.move(os.path.basename(recover_file_name),dst) 

def parse_command():
#    global backup_config
    backup_config = backup_config_struct()
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('mode', help='operation mode')
    parser.add_argument('backup_top', help='backup tp directory')
    parser.add_argument('-p','--password', help='password for 7zip')
    parser.add_argument('-t','--restore_time', help='specify time point YYYY/MM/DD-HH:MM:SS to restore ')
    parser.add_argument('-c','--config_file', nargs='+', help='specify config file')
    parser.add_argument('-w','--wait_sec', help='wait this before exit')
    parser.add_argument('--overwrite', action="store_true", help='overwrite existing files in restore mode')
    parser.add_argument('--full_path', action="store_true", help='full path')
    parser.add_argument('--delete_on_fail', action="store_true", help='delete archive if some error happends')
    parser.add_argument('--silent', action="store_true", help='No beep when finished')
    parser.add_argument('-f','--recovery_files', nargs='+', help='specify files or @file_list to recover')
    args = parser.parse_args() #,action="store_true"

    if (len(sys.argv)==1) or (not args.mode) or (not args.backup_top):
        print("Usage incbackup.py backup|empty|restore|list|verify dst_root -opts file1 file2 @fileslist")
        print("In restore mode,restore files to current directory")
        print(" -p password")
        print(" -t YYYY/MM/DD-HH:MM:SS restore to this time point.")
        print(" -overwrite restore overwriting existing old files.")
        print(" -fullpath restore with fullpath.(other wise filename only)")
#        print("In verify mode, type incbackup.py verify /media/usr/usbdisk/info_only_folder")
        exit(1)
    mode = args.mode
    if mode not in ["backup","empty","restore","list","history","verify"]:
        print("mode must be backup|empty|restore|list|history")
        exit(1)

    dst_root = args.backup_top
    if dst_root[-1] not in ["/","\\"]:
        dst_root = dst_root + "/"
    
    backup_config_file = dst_root + backup_config.DEFAULT_CONFIG_FILE_NAME
    backup_config_files = []
    backup_config.ARCHIVE_FOLDER = dst_root + backup_config.ARCHIVE_FOLDER_NAME
    
    try:
        os.listdir(backup_config.ARCHIVE_FOLDER)
    except FileNotFoundError:
        logging.info("create " +backup_config.ARCHIVE_FOLDER)
        os.mkdir(backup_config.ARCHIVE_FOLDER)

    if args.password :
        backup_config.password = "-p"+args.password
    if args.restore_time:
        if mode not in ["restore","list"]:
            print("-t YYYY/MM/DD-HH:MM:SS must be used with restore or list")
        else:
            backup_config.RECOVERY_TIME = str2time(args.restore_time)
    if args.overwrite:
        if mode not in ["restore"]:
            print("-overwrite must be used with restore or list")
        else:
            backup_config.OVERWRITE_OPT = ["-aoa"]
    if args.full_path:
        if mode not in ["restore"]:
            print("-fullpath must be used with restore or list")
        backup_config.EXTRACT_METHOD = "x"
    if args.delete_on_fail:
        backup_config.DELETE_ON_FAIL = True
    if args.silent:
        backup_config.DO_BEEP = False
    if args.wait_sec: ## w5 w1.5
        backup_config.WAIT_SEC_BEFORE_EXIT = float(args.wait_sec)
    if args.config_file:
        for backup_config_file in args.config_file:
            if not (backup_config_file[0]=='/' or backup_config_file[1:3]==':\\' or backup_config_file[1:3]==':/') : # not from root directory
                backup_config_file = dst_root + backup_config_file  ## relative to dst_root
            backup_config_files.append(backup_config_file)
    if args.recovery_files:
        for recover_file in args.recovery_files:
            if recover_file[0] == "@":
                f = open(recover_file[1:],encoding="utf8")
                lines = f.read().split("\n")
                f.close()
                for l in lines:
                    if l != "":                
                        backup_config.recovery_files.append(get_proper_pathname(recover_file))
            else:
                backup_config.recovery_files.append(get_proper_pathname(recover_file))

    if len(backup_config_files)==0:
        backup_config_files.append(backup_config_file)
    print("use ")
    for bc in backup_config_files:
        print(" %s"%bc)
    print("as config files. (if conflicts, below overwrite above) ")
        
    backup_config.read_config_files(backup_config_files)

    if mode=="backup" or mode=="restore" or mode=="list" or mode=="history" :
        try:
            create_path(backup_config.WORKDIR)
        except FileExistsError:
            pass

    backup_config.RESTORE_LIST_FILE = backup_config.WORKDIR + backup_config.RESTORE_LIST_FILE

    backup_config.BACKUP_STOP_FOLDER = list(backup_config.dst_top.keys())
    for f in backup_config.BACKUP_STOP_FOLDER:
        if backup_config.dst_top[f] in [[".+"],[".*"]]:
            backup_config.dst_top.pop(f)

    logger.debug("BACKUP_STOP_FOLDER=%s"%backup_config.BACKUP_STOP_FOLDER)
    backup_config.mode = mode
    return(backup_config)

if __name__ == '__main__':
    logging.basicConfig( level=logging.WARNING,format='%(asctime)s %(name)s %(message)s')
    logger = logging.getLogger('bklogging')
    
    try:
        backup_config = parse_command()    
        ref_time = time.time()
    
        backuped_files = create_backup_file_obj(backup_config.ARCHIVE_FOLDER,backup_config.RECOVERY_TIME)
        if backup_config.mode=="history":
            history()
        else:
            backuped_files.reconstruct_incremental(backup_config.ARCHIVE_FOLDER,backup_config.ARCHIVE_FILE_INFO_NAME )
    
            print("Reconstruct %.2f sec"%(time.time()-ref_time))
            if backup_config.mode == "backup" or backup_config.mode=="empty":
                backup(backup_config.mode)
            elif backup_config.mode=="restore" or backup_config.mode=="list":
                restore(backup_config.mode)
            elif backup_config.mode=="verify" :
                verify()
    
        print("total %.2f sec"%(time.time()-ref_time))
        feedbackbeep(True)
        time.sleep(backup_config.WAIT_SEC_BEFORE_EXIT)
        if backup_config.mode=="backup" or backup_config.mode=="restore" or backup_config.mode=="list" or backup_config.mode=="history" :
            if not backup_config.mode=="backup":
                input("Hit ret to erase %s"%backup_config.WORKDIR)
            shutil.rmtree(backup_config.WORKDIR)

    except:
        error = sys.exc_info()
        logger.warning('%s %s %s'%(error[0],error[1],traceback.extract_tb(error[2])))
        feedbackbeep(False)
else:
    logger = logging.getLogger('bklogging')

