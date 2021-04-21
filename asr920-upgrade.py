##########################################################################
#Script to upgrade ASR920 in bulk
#Author       : Rik Harms
#Version      : 0.6
#Date         : 4-1-2021
#
#See bottom of script for instructions
##########################################################################

#Import Modules
from netmiko import ConnectHandler
from netmiko import SCPConn
from getpass import getpass
import configparser
import re
import datetime
import time
import socket
import os
import getpass
from pythonping import ping
import sys
import concurrent.futures
import paramiko
import netmiko
import subprocess

#Define variables
init_file = 'asr920-upgrade.ini'                                    # Create ini file in same folder as python script, or specify path to ini file.
init = configparser.ConfigParser()
init.read(init_file)
device_type_telnet =  "cisco_ios_telnet"
device_type_ssh =  "cisco_ios_ssh"
filelocation = '/opt/ftp/cisco-sw/'                                  #this is the ftp folder and subfolder to place IOS-XE image.
image_file = init.get('image', 'image_file')
md5_image = init.get('image', 'md5_image')
rommon_file = init.get('rommon', 'rommon_file')
rommon_version = init.get('rommon', 'rommon_version')
rommon_version_reg =  rommon_version.replace('(','\(').replace(')','\)')
rommon_version_2 = init.get('rommon', 'rommon_version_2')
rommon_version_2_reg =  rommon_version_2.replace('(','\(').replace(')','\)')
rommon_version_3 = init.get('rommon', 'rommon_version_3')
rommon_version_3_reg =  rommon_version_3.replace('(','\(').replace(')','\)')
md5_rommon = init.get('rommon', 'md5_rommon')
#logfile = '/opt/ftp/asr920-upgrade/asr920-upgrade.log' 
currenttime = datetime.datetime.now().strftime("%Y_%m_%d_%H-%M")


#################################################################################Define Functions#############################################################################

def net_connect_session(host,type,global_delay_factor):
    try:
        net_connect_session = ConnectHandler(host=host, device_type=type, username=username, password=password,global_delay_factor=global_delay_factor)
        status = True
    except paramiko.ssh_exception.AuthenticationException:
        #print(f'{host}: Authentication failed\n')
        net_connect_session = (f'{host}: Authentication failed')
        status = False
    except netmiko.ssh_exception.NetmikoTimeoutException:
        #print(f'{host}: Timeout/DNS\n')
        net_connect_session = (f'{host}: Timeout/DNS')
        status = False
    return(net_connect_session,status)

def write_mem(net_connect):
    net_connect.save_config()

def set_ftp_source_int(net_connect):
    output = net_connect.send_command('sh ip vrf MANAGEMENT | include MANA')
    int = re.search('[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}:[0-9]{1,3}\s+([A-Z0-9]+)',output)[1]
    net_connect.config_mode()
    net_connect.send_command(f'ip ftp source-interface {int}')
    net_connect.send_command(f'ip ftp username {username}')
    net_connect.send_command(f'ip ftp password {ftp_password}')
    net_connect.exit_config_mode()

def set_ftp_creds(net_connect):
    net_connect.config_mode()
    net_connect.send_command(f'ip ftp username {username}')
    net_connect.send_command(f'ip ftp password {ftp_password}')
    net_connect.exit_config_mode()

def delete_ftp_creds(net_connect):
    net_connect.config_mode()
    net_connect.send_command('no ip ftp username ')
    net_connect.send_command('no ip ftp password ')
    net_connect.exit_config_mode()

def set_timeout(net_connect):
    net_connect.config_mode()
    net_connect.send_command('line vty 0 15',expect_string=r'config-line')
    net_connect.send_command('exec-timeout 0',expect_string=r'config-line')
    net_connect.exit_config_mode()
    
def restore_timeout(net_connect):
    net_connect.config_mode()
    net_connect.send_command('line vty 0 15',expect_string=r'config-line')
    net_connect.send_command('exec-timeout 15',expect_string=r'config-line')
    net_connect.exit_config_mode()

def current_version(net_connect):
    result = net_connect.send_command(f'show ver | include RELEASE SOFTWARE')
    ios_version = re.search('([0-9]+\.[0-9]+\.[0-9]+)',result)[0]
    return(ios_version)

def boot_parameter(net_connect):
    result = net_connect.send_command(f'sh bootvar | include BOOT variable =')
    boot_parameter = re.findall('(asr920[a-z0-9-_\.A-Z]+)',result)
    return(boot_parameter)

def find_files(net_connect):
    result = net_connect.send_command("dir bootflash: | include pkg|bin")
    find_files = re.findall('(asr920[a-z0-9-_\.A-Z]+)',result)
    return find_files

def check_file_exist(net_connect,file):
    result = net_connect.send_command("dir bootflash:")
    if re.search(file,result):
        result = True
    else:
        result = False
    return result

def delete_file(net_connect,file):
    output = net_connect.send_command(f'delete /force bootflash:{file}')
    check = net_connect.send_command(f'sh bootflash: | include {file}')
    if re.search(file,check):
        result = False
    else:
        result = True
    return result
    
def verify_space(net_connect,file):
    file_path = filelocation+file
    result = net_connect.send_command("dir bootflash:")
    reg = re.compile(r'(\d+)\sbytes\sfree')
    space = int(reg.findall(result)[0])
    f_size = os.path.getsize(file_path)
    if space >= f_size:
        result = True
    elif space < f_size:
        result = False
    return result

def verify_md5(net_connect,file,md5):
    result = net_connect.send_command("verify /md5 flash:{} {}".format(file,md5))
    reg = re.compile(r'Verified')
    verify = reg.findall(result)
    if verify:
        result = True
    else:
        result = False
    return result

def transfer_file(net_connect,file):
    result = net_connect.send_command(f'copy ftp://198.18.1.15/cisco-sw/{file} bootflash:{file}',expect_string=r'#|Destination',delay_factor=20)
    if re.search('Destination',result):
        result1 = net_connect.send_command('\n',expect_string=r'#',delay_factor=10)
        if re.search('OK',result1):
            result = True
    elif re.search('OK',result):
        result = True
    else:
        result = False
    return result

def upgrade_rommon(host,file):
    log = open(logfile,'a')
    print(f'{host}: Upgrading Rommon')
    log.write(f'{host}: Upgrading Rommon\n')
    #net_connect_upgrade = ConnectHandler(host=host, device_type=device_type_ssh, username=username, password=password,global_delay_factor=20)
    net_connect_upgrade, net_connect_upgrade_status = net_connect_session(host,device_type_ssh,20)
    result = net_connect_upgrade.send_command(f'show platform')
    rommon_version = re.search('[0-9][0-9].[0-9]\(.+\)S',result)[0]
    if re.search(rommon_version_reg,result) or re.search(rommon_version_2_reg,result) or re.search(rommon_version_3_reg,result):
        print(f'{host}: Rommon already on correct/accepted version: {rommon_version}')
        log.write(f'{host}: Rommon already on correct/accepted version: {rommon_version}\n')
        net_connect_upgrade.disconnect()
        result = 'Skipped'
    else:
        result = net_connect_upgrade.send_command(f'upgrade rom-monitor filename bootflash:{file} all',expect_string=r'#',delay_factor=10)
        #result = 'ROMMON upgrade complete'
        if 'ROMMON upgrade complete' in result:
            print(f'{host}: Rommon upgraded, reloading device. this can take up to 15 minutes.')
            log.write(f'{host}: Rommon upgraded, reloading device. this can take up to 15 minutes.\n')
            #Save config
            net_connect_upgrade.send_command('wr')
            reload = net_connect_upgrade.send_command('reload reason upgrade rommon',expect_string=r'confirm|modified',delay_factor=10)
        if 'System configuration has been modified. Save? [yes/no]' in reload:
            print(f'{host}: saving config')
            reload = net_connect_upgrade.send_command('yes',expect_string=r'confirm')

        if 'confirm' in reload:
            try:
                net_connect_upgrade.send_command('\n')
            except:
                pass
            print(f'{host}: reloading')
            log.write(f'{host}: reloading')
            
        time.sleep(900)
        print(f'{host}: attempt 1')
        log.write(f'{host}: attempt 1\n')
        ping = subprocess.Popen(['ping', '-c', '3', host], stdout=subprocess.PIPE)
        stdout, stderr = ping .communicate()
        if ping.returncode == 0:
            status = True
        else:
            print(f'{host}: not back yet, wating another 5 minutes ')
            time.sleep(300)
            ping = subprocess.Popen(['ping', '-c', '3', host], stdout=subprocess.PIPE)
            stdout, stderr = ping.communicate()
            if ping.returncode == 0:
                status = True
            else:
                print(f'{host}: not back yet, wating another 5 minutes ')
                time.sleep(300)
                ping = subprocess.Popen(['ping', '-c', '3', host], stdout=subprocess.PIPE)
                stdout, stderr = ping.communicate()
                if ping.returncode == 0:
                    status = True
                else:
                    print(f'{host} : no response to ping. upgrade failed')
                    log.write(f'{host} : no response to ping. upgrade failed\n')
                    status = False
                    
        # response = os.system("ping -c1 -W1 " + host)
        # if response == 0:
            # result = 'Success'
        # else:
            # print(f'{host}: not back yet, wating another 5 minutes ')
            # time.sleep(300)
            # response = os.system("ping -c1 -W1 " + host)
            # if response == 0:
                # result = 'Success'
            # else:
                # time.sleep(300)
                # response = os.system("ping -c1 -W1 " + host)
                # if response == 0:
                    # result = 'Success'
                # else:
                    # print(f'{host} : no response to ping. upgrade failed')
                    # log.write(f'{host} : no response to ping. upgrade failed\n')
                    # result = 'Failure'
                    # prep_thread.set_exception('TESTFAIL')
        if result:
            #try connecting again
            #net_connect_check_rommon = ConnectHandler(host=host, device_type=device_type_ssh, username=username, password=password)
            net_connect_check_rommon, net_connect_check_rommon_status = net_connect_session(host,device_type_ssh,0.1)
            result = net_connect_check_rommon.send_command(f'show platform')
            rommon_version = re.search('[0-9][0-9].[0-9]\(.+\)S',result)[0]
            net_connect_check_rommon.disconnect()
            if re.search(rommon_version_reg,result):
                print(f'{host}: Rommon upgraded: {rommon_version}')
                log.write(f'{host}: Rommon upgraded: {rommon_version}\n')
                result = 'Success'
            else:
                result = 'Failure'
                print(f'{host}: Rommon NOT upgraded. Failed')
                log.write(f'{host}: Rommon NOT upgraded. Failed\n')
        else:
            print(f'{host}: Rommon NOT upgraded. Failed')
            log.write(f'{host}: Rommon NOT upgraded. Failed\n')
            result = 'Failure'
    return result
    log.close() 
    
def upgrade_ios(host,file):
    log = open(logfile,'a')
    print(f'{host}: Upgrading IOS')
    log.write(f'{host}: Upgrading IOS\n')
    #net_connect_upgrade = ConnectHandler(host=host, device_type=device_type_ssh, username=username, password=password,global_delay_factor=10)
    net_connect_upgrade, net_connect_upgrade_status = net_connect_session(host,device_type_ssh,20)
    result = net_connect_upgrade.send_command(f'sh ver | include System image file')
    ios_version = net_connect_upgrade.send_command(f'show ver | include RELEASE SOFTWARE')
    ios_version = re.search('([0-9]+\.[0-9]+\.[0-9]+)',ios_version)[0]
    if re.search(image_file,result):
        print(f'{host}: IOS already on correct version: {ios_version}')
        log.write(f'{host}: IOS already on correct version: {ios_version}\n')
        net_connect_upgrade.disconnect()
        result = 'Skipped'
    else:
        print(f'{host}: Changing bootparameters')
        #Set Bootparameters, before current version
        resultcurrentboot = net_connect_upgrade.send_command(f'sh run | include boot system').split('\n')
        net_connect_upgrade.config_mode()
        for lines in resultcurrentboot:
            net_connect_upgrade.send_command(f'no {lines}')

        net_connect_upgrade.send_command(f'boot system bootflash:{image_file}')

        for lines in resultcurrentboot:
            net_connect_upgrade.send_command(f'{lines}')
            
        net_connect_upgrade.exit_config_mode()
        net_connect_upgrade.send_command('wr')

        print(f'{host}: Boot parameters changed, reloading device. this can take up to 15 minutes.')
        log.write(f'{host}: Boot parameters changed, reloading device. this can take up to 15 minutes.\n')
        reload = net_connect_upgrade.send_command('reload reason upgrade IOS',expect_string=r'confirm|modified')
        if 'System configuration has been modified. Save? [yes/no]' in reload:
            print(f'{host}: saving config')
            log.write(f'{host}: saving config\n')
            reload = net_connect_upgrade.send_command('yes',expect_string=r'confirm')

        if 'confirm' in reload:
            try:
                net_connect_upgrade.send_command('\n')
            except:
                pass
            print(f'{host}: reloading')
            log.write(f'{host}: reloading\n')
        
        time.sleep(900)
        print(f'{host}: attempt 1')
        log.write(f'{host}: attempt 1\n')
        
        ping = subprocess.Popen(['ping', '-c', '3', host], stdout=subprocess.PIPE)
        stdout, stderr = ping .communicate()
        if ping.returncode == 0:
            status = True
        else:
            print(f'{host}: not back yet, wating another 5 minutes ')
            time.sleep(300)
            ping = subprocess.Popen(['ping', '-c', '3', host], stdout=subprocess.PIPE)
            stdout, stderr = ping.communicate()
            if ping.returncode == 0:
                status = True
            else:
                print(f'{host}: not back yet, wating another 5 minutes ')
                time.sleep(300)
                ping = subprocess.Popen(['ping', '-c', '3', host], stdout=subprocess.PIPE)
                stdout, stderr = ping.communicate()
                if ping.returncode == 0:
                    status = True
                else:
                    print(f'{host} : no response to ping. upgrade failed')
                    log.write(f'{host} : no response to ping. upgrade failed\n')
                    status = False
        # response = os.system("ping -c1 -W1 " + host)
        # if response == 0:
            # status = True
        # else:
            # time.sleep(300)
            # print(f'{host}: not back yet, wating another 5 minutes ')
            # response = os.system("ping -c1 -W1 " + host)
            # if response == 0:
                # status = True
            # else:
                # time.sleep(300)
                # response = os.system("ping -c1 -W1 " + host)
                # if response == 0:
                    # status = True
                # else:
                    # print(f'{host} : no response to ping. upgrade failed')
                    # log.write(f'{host} : no response to ping. upgrade failed\n')
                    # status = False
        if status:
            #try connecting again
            #net_connect_check_ios = ConnectHandler(host=host, device_type=device_type_ssh, username=username, password=password,global_delay_factor=10)
            net_connect_check_ios, net_connect_check_ios_status = net_connect_session(host,device_type_ssh,0.1)
            result = net_connect_check_ios.send_command(f'show version | include System image file')
            ios_version = net_connect_check_ios.send_command(f'show ver | include RELEASE SOFTWARE')
            ios_version = re.search('([0-9]+\.[0-9]+\.[0-9]+)',ios_version)[0]
            net_connect_check_ios.disconnect()
            if re.search(image_file,result):
                print(f'{host}: IOS succesfully upgraded to : {ios_version}')
                log.write(f'{host}: IOS succesfully upgraded to : {ios_version}\n')
                result = 'Success'
            else:
                result = 'Failure'
                print(f'{host}: IOS NOT upgraded. Failed')
                log.write(f'{host}: IOS NOT upgraded. Failed\n')
        else:
            print(f'{host}: IOS NOT upgraded. Failed')
            log.write(f'{host}: IOS NOT upgraded. Failed\n')
            result = 'Failure'
    return result
    log.close() 

###############define MAIN FUNCTION############################
def main(host,image_file):
    host = host.strip()
    log = open(logfile,'a')
    print(f'{host}: Connecting')
    log.write(f'{host}: Connecting\n')
    net_connect_slow, net_connect_slow_status = net_connect_session(host,device_type_ssh,20)
    net_connect_fast, net_connect_fast_status = net_connect_session(host,device_type_ssh,0.1)
    if not net_connect_slow_status and not net_connect_fast_status:
        print(net_connect_fast)
        log.write(net_connect_fast)
        hostlist.remove(host)
        failedhostlist.append(host)
    if net_connect_slow_status and net_connect_fast_status:
        print(f'{host}: Connected')
        log.write(f'{host}: Connected\n')
        #Disable vty timeout to prevent losing session
        disable_timout = set_timeout(net_connect_fast)
        #Cleanup flash first
        current_ios_version = current_version(net_connect_fast)
        bootvar_parameter = boot_parameter(net_connect_fast)
        files = find_files(net_connect_fast)
        print(f'{host}: Looking for files to delete.')
        log.write(f'{host}: Looking for files to delete.\n')
        for file in files:
            if re.search(rommon_file,file):
                print(f'{host}: Rommon file to be installed found. Skipping delete.')
                log.write(f'{host}: Rommon file to be installed found. Skipping delete.\n')
            elif re.search('pkg',file) and not re.search(rommon_file,file):
                print(f'{host}: Old rommon found({file}). Deleting file.')
                log.write(f'{host}: Old rommon found({file}). Deleting file.\n')
                delete_file(net_connect_fast,file)
            elif re.search(image_file,file):
                print(f'{host}: Image file to be installed found. Skipping delete.')
                log.write(f'{host}: Image file to be installed found. Skipping delete.\n')
            elif re.search('bin',file) and not re.search(image_file,file):
                if file in bootvar_parameter:
                    print(f'{host}: image found in bootparameters({file}). Skipping delete.')
                    log.write(f'{host}: image found in bootparameters({file}). Skipping delete.\n')
                else:
                    print(f'{host}: image NOT found in bootparameters({file}). Deleting file.')
                    log.write(f'{host}: image NOT found in bootparameters({file}). Deleting file.\n')
                    delete_file(net_connect_fast,file)
        #IMAGE FILE
        check_exist_image = check_file_exist(net_connect_fast,image_file)
        if check_exist_image:
            print(f'{host}: Image file already exists')
            log.write(f'{host}: Image file already exists \n')
            #Check if MD5 is ok
            check_md5 = verify_md5(net_connect_slow, image_file,md5_image)
            if check_md5:
                print(f'{host}: MD5 image succesfull')
                log.write(f'{host}: MD5 image succesfull\n')
                pass
            else:
                print(f'{host}: MD5 image unsuccesfull. Deleting file')
                log.write(f'{host}: MD5 image unsuccesfull. Deleting file\n')
                delete_file(net_connect_fast,image_file)          
                pass
        else:
            print(f'{host}: Image file not present, checking available space')
            log.write(f'{host}: Image file not present, checking available space\n')
            #Check if enough space is available
            ver_space = verify_space(net_connect_fast,image_file) 
            if ver_space:
                print(f'{host}: available space ok. start transfer')
                log.write(f'{host}: available space ok. start transfer\n')
                #Check/set ftp source interface
                set_ftp_source_int(net_connect_fast)
                set_ftp_creds(net_connect_fast)
                #Download Image to flash
                transfer_image = transfer_file(net_connect_slow,image_file)
                if transfer_image:
                    print(f'{host}: Image file download succesfull')
                    log.write(f'{host}: Image file download succesfull\n')
                    check_md5 = verify_md5(net_connect_slow, image_file,md5_image)
                    if check_md5:
                        print(f'{host}: MD5 image succesfull')
                        log.write(f'{host}: MD5 image succesfull\n')
                        pass
                    else:
                        print(f'{host}: MD5 image unsuccesfull. Deleting file')
                        log.write(f'{host}: MD5 image unsuccesfull. Deleting file\n')
                        delete_file(net_connect_fast,image_file) 
                        pass
                else:
                    print(f'{host}: Image download failed')
                    log.write(f'{host}: Image download failed\n')
            else:
                print(f'{host}: Not enough space on device')
                log.write(f'{host}: Not enough space on device\n')
        #ROMMON FILE
        check_exist_image = check_file_exist(net_connect_fast,rommon_file)
        if check_exist_image:
            print(f'{host}: Rommon file already exists')
            log.write(f'{host}: Rommon file already exists \n')
            #Check if MD5 is ok
            check_md5 = verify_md5(net_connect_fast, rommon_file,md5_rommon)
            if check_md5:
                print(f'{host}: MD5 Rommon succesfull')
                log.write(f'{host}: MD5 Rommon succesfull\n')
                pass
            else:
                print(f'{host}: MD5 Rommon unsuccesfull. Deleting file')
                log.write(f'{host}: MD5 Rommon unsuccesfull. Deleting file\n')
                delete_file(net_connect_fast,rommon_file) 
                pass
        else:
            print(f'{host}: Rommon file not present, checking available space')
            log.write(f'{host}: Rommon file not present, checking available space\n')
            #Check if enough space is available
            ver_space = verify_space(net_connect_fast,rommon_file) 
            if ver_space:
                print(f'{host}: available space ok. start transfer')
                log.write(f'{host}: available space ok. start transfer\n')
                #Check/set ftp source interface
                set_ftp_source_int(net_connect_fast)
                set_ftp_creds(net_connect_fast)
                #Download Rommon to flash
                transfer_rommon = transfer_file(net_connect_slow,rommon_file)
                if transfer_rommon:
                    print(f'{host}: Rommon file download succesfull')
                    log.write(f'{host}: Rommon file download succesfull\n')
                    check_md5 = verify_md5(net_connect_fast, rommon_file,md5_rommon)
                    if check_md5:
                        print(f'{host}: MD5 Rommon succesfull')
                        log.write(f'{host}: MD5 Rommon succesfull\n')
                        pass
                    else:
                        print(f'{host}: MD5 Rommon unsuccesfull. Deleting file')
                        log.write(f'{host}: MD5 Rommon unsuccesfull. Deleting file\n')
                        delete_file(net_connect_fast,rommon_file) 
                        pass
                else:
                    print(f'{host}: Rommon download failed')
                    log.write(f'{host}: Rommon download failed\n')
        print(f'{host}: Finished prepping')
        log.write(f'{host}: Finished prepping\n')
        #Restore vty timeout
        restore_timeout(net_connect_fast)
        #Delete ftp credentials
        delete_ftp_creds(net_connect_fast)
        #print(f'{host}: Saving configuration\n')
        #log.write(f'{host}: Saving configuration\n')
        #write_mem(net_connect_slow)
        net_connect_slow.disconnect()
        net_connect_fast.disconnect()
    log.close() 
    
##################################################################################################START MAIN#########################################################################

print('#'*100)
print('#'+' '*98+'#')
print('#'+' '*98+'#')
print('#'+' '*20+'Script to upgrade ASR920 CPE`s in bulk'+' '*40+'#')
print('#'+' '*98+'#')
print('#'+' '*98+'#')
print('#'*100+'\n')

# Get Username and Password
username = input('Please enter your username: ')
password = getpass.getpass('Please enter your password: ')
ftp_password = getpass.getpass('Please enter your FTP password (same as login to portal): ')
#print('\n')
# Get input file
input_try = 0
while input_try <= 2:
    hostfile = input('Enter file with CPE`s to be upgraded: ')
    if os.path.isfile(hostfile):
        #print(f'\nFile to be used: {hostfile}\n')
        break
    else:
        print(f'File {hostfile} not found. try again\n')
        input_try += 1

if input_try == 3:
    sys.exit('Too many Tries. exiting script')

#Create list with CPE`s
hostlist = []
hostlistfile = open(hostfile,'r')

for host in hostlistfile:
    host = host.strip()
    hostlist.append(host.strip())

#How many concurent threads for upgrading, default = 5
max_threads = input('Specify number of cpe`s per thread for prepping. (Default = 10): ')
if max_threads == '':
    max_threads = 10
else:
    max_threads = int(max_threads)

#Define logfile
logfile = f'/opt/ftp/asr920-upgrade/log/asr920_upgrade_{hostfile}.{currenttime}.log'

#Get upgrade selection choice
upgrade = input('Do you want to upgrade after prepping the devices? (Y/N): ')

if upgrade == '':
    upgrade = False
if upgrade == 'N':
    upgrade = False
if upgrade == 'n':
    upgrade = False
if upgrade == 'Y':
    upgrade = True
if upgrade == 'y':
    upgrade = True


#print('\n')
if upgrade:
    upgradecheck = input('Are you sure? devices will be rebooted? (Y/N): ')
    if upgradecheck == '':
        upgrade = False
    if upgradecheck == 'N':
        upgrade = False
    if upgradecheck == 'n':
        upgrade = False
    if upgradecheck == 'Y':
        upgrade = True
    if upgradecheck == 'y':
        upgrade = True
        
#How many cpe`s per thread for upgrading, default = 5
if upgrade:
    max_cpe_per_thread_upgrade = input('Specify number of cpe`s per thread for upgrading. (Default = 5): ')
    if max_cpe_per_thread_upgrade == '':
        max_cpe_per_thread_upgrade = 5
    else:
        max_cpe_per_thread_upgrade = int(max_cpe_per_thread_upgrade)

if upgrade:
    max_fail = input('Enter max allowed failures before ending script (default =2): ')
    if max_fail == '':
        max_fail = 2
    else:
        max_fail = int(max_fail)
    
if upgrade: 
    upgradeselect = 'Selection: Yes, CPE`s will be rebooted and upgraded.!!!\n'      
else:
    upgradeselect = 'Selection: No, CPE`s will NOT be rebooted and upgraded\n'

log = open(logfile,'w')

print('\n')
log.write('\n')
print('#'*35+'Summary'+'#'*35+'\n')
log.write('#'*35+'Summary'+'#'*35+'\n')
print(f'Image file: {image_file}\n')
log.write(f'Image file: {image_file}\n')
print(f'Md5 image file : {md5_image}\n')
log.write(f'Md5 image file: {md5_image}\n')
print(f'Rommon: {rommon_file}\n')
log.write(f'Rommon file: {rommon_file}\n')
print(f'Md5 rommon file: {md5_rommon}\n')
log.write(f'Md5 rommon file: {md5_rommon}\n')
print(f'input file : {hostfile}\n')
log.write(f'input file : {hostfile}\n')
print(f'nr of CPE`s in file : {len(hostlist)}\n')
log.write(f'nr of CPE`s in file : {len(hostlist)}\n')
print(f'Logfile : {logfile}\n')
log.write(f'Logfile : {logfile}\n')
print(upgradeselect)
log.write(upgradeselect)
print(f'Number of cpe`s per thread for prepping: {max_threads}\n')
log.write(f'Number of cpe`s per thread for prepping: {max_threads}\n')
if upgrade:
    print(f'Number of cpe`s per thread for upgrade: {max_cpe_per_thread_upgrade}\n')
    log.write(f'Number of cpe`s per thread for upgrade: {max_cpe_per_thread_upgrade}\n')
    print(f'Max numer of upgrade failures before ending script: {max_fail}\n')
    log.write(f'Max numer of upgrade failures before ending script: {max_fail}\n')
    
print('\n')
print('#'*70+'\n')
log.write('#'*70+'\n')

input('Press enter key to continue.\n')
###########################Start Prepping
print('#'*25+' Start Prepping '+'#'*25+'\n')
log.write('#'*25+' Start Prepping '+'#'*25+'\n')
log.close()
failedhostlist = []


with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
    prep_thread = {executor.submit(main, host, image_file): host for host in hostlist}

log = open(logfile,'a')
print('#'*25+' Finished Prepping '+'#'*30+'\n')
log.write('#'*25+' Finished  Prepping '+'#'*30+'\n')
log.close()
#################Start with Upgrading
if upgrade:
    cpe_rommon_success = []
    cpe_rommon_fail = []
    cpe_rommon_skipped = []
    listcounter = 1
    fail_count = 0

    #Make sublist of hostlis
    hostlist_chunk = [hostlist[x:x+max_cpe_per_thread_upgrade] for x in range(0, len(hostlist), max_cpe_per_thread_upgrade)]

    #ROMMON
    log = open(logfile,'a')
    print('#'*25+' Start Upgrading Rommon '+'#'*25+'\n')
    log.write('#'*25+' Start Upgrading Rommon '+'#'*25+'\n')
    log.close()


    log = open(logfile,'a') 
    for list in hostlist_chunk:
        prep_thread = []
        if fail_count < max_fail:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                for host in list:
                    prep_thread.append(executor.submit(upgrade_rommon, host, rommon_file))
            for result in prep_thread:
                if 'Failure'in result.result():
                    fail_count += 1
                    cpe_rommon_fail.append(result.result())
                elif 'Skipped'in result.result():
                    cpe_rommon_skipped.append(result.result())
                else:
                    cpe_rommon_success.append(result.result())
            listcounter += 1
        else:
            #print(f'Max numer of failures reached: {fail_count}. Ending script\n')
            log.write(f'Max numer of failures reached: {fail_count}. Ending script\n')
            break

    log = open(logfile,'a')        
    print('#'*25+'Finished upgrading Rommon'+'#'*25+'\n')
    log.write('#'*25+'Finished upgrading Rommon'+'#'*25+'\n')


    ###IOS
    cpe_ios_success = []
    cpe_ios_fail = []
    cpe_ios_skipped = []
    log = open(logfile,'a')
    print('#'*25+' Start Upgrading IOS '+'#'*25+'\n')
    log.write('#'*25+' Start Upgrading IOS '+'#'*25+'\n')
    log.close()

    log = open(logfile,'a')

    if fail_count < max_fail:
        for list in hostlist_chunk:
            ios_thread = []
            if fail_count < max_fail:
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor1:
                    for host in list:
                        ios_thread.append(executor1.submit(upgrade_ios, host, image_file))
                for result in ios_thread:
                    if 'Failure'in result.result():
                        fail_count += 1
                        cpe_ios_fail.append(result.result())
                    elif 'Skipped'in result.result():
                        cpe_ios_skipped.append(result.result())
                    else:
                        #print(result.result())
                        cpe_ios_success.append(result.result())
                listcounter += 1
            else:
                end_script = True 
                break

    log = open(logfile,'a')        
    print('#'*25+' Finished upgrading IOS '+'#'*25+'\n')
    log.write('#'*25+' Finished upgrading IOS '+'#'*25+'\n')

    ###SUMMARY
    print('#'*25+' Summary '+'#'*25+'\n')
    log.write('#'*25+' Summary '+'#'*25+'\n')
    print(f'nr. of CPE`s succesfull Rommon upgrade: {len(cpe_rommon_success)}')
    log.write(f'nr. of CPE`s succesfull Rommon upgrade: {len(cpe_rommon_success)}\n')
    print(f'nr. of CPE`s skipped Rommon upgrade: {len(cpe_rommon_skipped)}')
    log.write(f'nr. of CPE`s skipped Rommon upgrade: {len(cpe_rommon_skipped)}\n')
    print(f'nr. of CPE`s failed Rommon upgrade: {len(cpe_rommon_fail)}')
    log.write(f'nr. of CPE`s failed Rommon upgrade: {len(cpe_rommon_fail)}\n')
    print(f'nr. of CPE`s succesfull IOS upgrade: {len(cpe_ios_success)}')
    log.write(f'nr. of CPE`s succesfull IOS upgrade: {len(cpe_ios_success)}\n')
    print(f'nr. of CPE`s skipped IOS upgrade: {len(cpe_ios_skipped)}')
    log.write(f'nr. of CPE`s skipped IOS upgrade: {len(cpe_ios_skipped)}\n')
    print(f'nr. of CPE`s failed IOS upgrade: {len(cpe_ios_fail)}')
    log.write(f'nr. of CPE`s failed IOS upgrade: {len(cpe_ios_fail)}\n')
    print(f'nr. of CPE`s failed connection: {len(failedhostlist)}')
    log.write(f'nr. of CPE`s failed connection: {len(failedhostlist)}\n')
    log.close()
  
print('End of Script')
  
  
    
################################################END MAIN###################################
