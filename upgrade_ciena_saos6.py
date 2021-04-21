#!/usr/bin/python3.6
#Author: Rik Harms. VodafoneZiggo


from netmiko import ConnectHandler
from getpass import getpass
import datetime
import sys
import os
import getpass
import configparser
import re
import time
import subprocess
import difflib 
from deepdiff import DeepDiff

#Create functions

def ssh_connection(host):
    try:
        net_connect_ssh = ConnectHandler(host=host, device_type=device_type_ssh, username=username, password=password)
        if net_connect_ssh.is_alive():
            status = True
    except:
        status = False
        net_connect_ssh = False
    return(net_connect_ssh, status)

def check_saos6(session):
    get_saos = session.send_command('software show', expect_string='>')
    try:
        current_saos = re.search('(Running Package)\s+:\s([a-z-0-9]+)',get_saos)[2]
    except:
        saos6 = False
        current_saos = 'none_saos6'
    if re.search('saos-06',get_saos):
        saos6 = True
    else:
        saos6 = False
    return(saos6,current_saos)

def save_config(session):
    session.send_command('configuration save', expect_string='>')

def get_config(session):
    config = session.send_command('configuration show line-numbered', expect_string='>')
    return(config)

def mac_table(session):
    mac_table = session.send_command('flow mac-addr show', expect_string='>')
    return(mac_table)

def power_module(session):
    power_module = session.send_command('chassis show power', expect_string='>')
    power_A = re.search('PSA\s+\|\s+[A-Z\/0-9-]+\s+\|\s+[a-zA-Z]+\s+\|\s+([a-zA-Z]+)',power_module)[1]
    power_B = re.search('PSB\s+\|\s+[A-Z\/0-9-]+\s+\|\s+[a-zA-Z]+\s+\|\s+([a-zA-Z]+)',power_module)[1]
    if power_A == 'Online':
        power_A_state = True
    elif power_A == 'Offline':
        power_A_state = False
    else:
        power_A_state = False
    if power_B == 'Online':
        power_B_state = True
    elif power_B == 'Offline':
        power_B_state = False
    else:
        power_B_state = False
      
    if power_A_state and power_B_state:
        power = 'Ok'
        power_red = 'Ok'
    else:
        power = 'Not Ok'
    
    if not power_A_state:
        power_red = 'PSA offline'
    elif not power_B_state:
        power_red = 'PSB offline'

    return(power,power_red)

def get_ring_info(session):
    ring_info = session.send_command('ring-protection virtual-ring show', expect_string='>')
    return(ring_info)
    
# def ring_state(ssh_session):
    # ring_list = []
    # ring = get_ring_info(ssh_session)
    # ring_nr = re.findall('(V[MS]R[0-9]+)',ring)
    # if len(ring_nr) > 0:
        # for ring in ring_nr:
            # ring_state_get = ssh_session.send_command(f'ring-protection virtual-ring show ring {ring}', expect_string='>')
            # ring_state_list = ring_state_get.splitlines()
            # ring_list.append(ring_state_list)
            # for lines in ring_state_list:
                # if '| Status                   | ' in lines:
                    # ring_status_east = re.search('\| Status\s+\|\s([A-Za-z\s]+)+\|\s([A-Za-z\s]+)',lines)[1]
                    # ring_status_west = re.search('\| Status\s+\|\s([A-Za-z\s]+)+\|\s([A-Za-z\s]+)',lines)[2]
                    # if 'Ok' in ring_status_east and 'Ok' in ring_status_west:
                        # ring_state = True
                    # else:
                        # ring_state = False
    # else:
        # ring_state = True
        # ring_state_get = 'No ring configured on device'
        
    # return(ring_state,ring_state_get)
    
def ring_state(ssh_session):
    ring_list = []
    ring = get_ring_info(ssh_session)
    ring_nr = re.findall('(V[MS]R[0-9]+)',ring)
    if len(ring_nr) > 0:
        for ring in ring_nr:
            ring_state_get = ssh_session.send_command(f'ring-protection virtual-ring show ring {ring}', expect_string='>')
            ring_state_info = re.search('\| State\s{25}\s+\|\s([a-zA-Z]+)',ring_state_get)[1]
            if 'Ok' in ring_state_info:
                ring_state = True
            else:
                ring_state = False
    else:
        ring_state = True
        ring_state_get = 'No ring configured on device'
        
    return(ring_state,ring_state_get,ring_state_info)

def agg_state(session):
    agg_state = session.send_command('aggregation show', expect_string='>')
    return(agg_state)  

def port_state(session):
    port_state = session.send_command('port show', expect_string='>')
    return(port_state)       
    
def transfer_image(session,image):
    #PROD
    ssh_session.send_command(f'system xftp set ftp-server 172.22.170.30 login-id {ftp_username} password {ftp_password}', expect_string='>')
    #LAB
    #ssh_session.send_command(f'system xftp set ftp-server 172.22.170.4 login-id {ftp_username} password {ftp_password}', expect_string='>')
    ssh_session.send_command(f'software install package {image} default-ftp-server package-path /ciena/{image}/le-lnx.xml defer-activation', expect_string='>')

def upgrade_switch(session,image_file,host):
    ssh_session.send_command(f'system xftp set ftp-server 172.22.170.30 login-id {ftp_username} password {ftp_password}', expect_string='>')
    #LAB
    #ssh_session.send_command(f'system xftp set ftp-server 172.22.170.4 login-id {ftp_username} password {ftp_password}', expect_string='>')
    print(f'{host}: issueing software run command')
    try:
        ssh_session.send_command_timing(f'software run default-ftp-server command-file ciena/{image_file}/le-lnx.xml')
    except:
        pass
        print(f'Result: {result}')
    
def compare_pre_post_config(pre,post):
    pre = open(pre).readlines()
    post = open(post).readlines()
    diff = []
    if pre == post:
        status = True
    else:
        status = False
        #Diff files
        #print('Diff on files')
        for line in difflib.unified_diff(pre, post):
            if re.search('^[+-][^+-]',line):
                diff.append(line)
    return(status,diff)
    
def compare_pre_post_config_port(pre,post):
    pre = open(pre).readlines()
    post = open(post).readlines()
    port_pre = {}
    port_post = {}
    port_status = []
    for line in pre:
        if re.search('10Gig|Uncertif|LAG',line):
            port = re.search('^\|\s([0-9A-Z_]+)',line)
            #status = line[22:26].strip()
            status = re.search('(Up|Down)',line)
            #print(f'{port[1]},{status}')
            port_pre[port[1]] = status[1]
    for line in post:
        if re.search('10Gig|Uncertif|LAG',line):
            port = re.search('^\|\s([0-9A-Z_]+)',line)
            #status = line[22:26].strip()
            status = re.search('(Up|Down)',line)
            #print(f'{port[1]},{status}')
            port_post[port[1]] = status[1]
            
    diff = DeepDiff(port_pre, port_post)
    
    if len(diff) > 0:
        for item in diff['values_changed'].items():
            port = item[0].split("'")[1]
            status_pre = item[1]['old_value']
            status_post = item[1]['new_value']
            port_status.append(f'{port},{status_pre},{status_post}')
            status_port_diff = False            
    else:
        status_port_diff = True
    return(port_status, status_port_diff)

def compare_mac(mac_table_pre,mac_table_post):
    def vlan_list(mac_table):
        vlan_list = []
        for lines in mac_table.splitlines():
            if re.search('\| ([0-9]+)',lines):
                vlan = re.search('\| ([0-9]+)',lines)[1]
                vlan_list.append(vlan)
        vlan_list = set(vlan_list)
        return(vlan_list)
            
    def mac_count(vlan_list,mac_table):
        count_mac = {}
        for vlan in vlan_list:
            mac_counter = 0
            for mac in mac_table.splitlines():
                if re.search(f'^\|\s{vlan}\s+',mac):
                    mac = re.search('^\|[0-9\s]+\|\s([0-9a-zA-Z:]+).*',mac)[1]
                    mac_counter += 1
            count_mac[vlan] = mac_counter
        return(count_mac)
        
        
    vlan_list_pre = vlan_list(mac_table_pre)
    vlan_list_post = vlan_list(mac_table_post)
    mac_pre_count = mac_count(vlan_list_pre,mac_table_pre)
    mac_post_count = mac_count(vlan_list_pre,mac_table_post)
    
    diff = DeepDiff(mac_pre_count, mac_post_count)
    
    mac_status = []
    mac_status_bool = True
    if len(diff) > 0:
        for item in diff['values_changed'].items():
            vlan = item[0].split("'")[1]
            mac_pre = item[1]['old_value']
            mac_post = item[1]['new_value']
            mac_status.append(f'Vlan:{vlan},Pre-count:{mac_pre},Post-count:{mac_post}')
            mac_status_bool = False
    return(mac_status,mac_status_bool)
    
    
    
def clean_up(session):
    ssh_session.send_command('system xftp unset ftp-server', expect_string='>')
    ssh_session.send_command('configuration save', expect_string='>')

#Create some variables
init_file = 'upgrade_ciena_saos6.ini'                                    # Create ini file in same folder as python script, or specify path to ini file.
init = configparser.ConfigParser()
init.read(init_file)
device_type_ssh =  "ciena_saos_ssh"
currenttime = datetime.datetime.now().strftime("%Y_%m_%d_%H-%M")


#Get username and password for ssh and ftp
username = input('Please enter your username: ')
password = getpass.getpass('Please enter your password: ')
#LAB
ftp_username = 'rharms'
ftp_password = 'Change01'
#PROD
# ftp_username = 'bb_beheer'
# ftp_password = '827cb0eEhrtS'

#ftp_username = init.get('ftp', 'ftp_user')
#ftp_password = init.get('ftp', 'ftp_password')
image_file = init.get('image', 'image_file')
# print('''Select image to use.
# Enter 1 for saos-06-20-00-0211
# Enter 2 for saos-06-16-00-0265
# ''')
# image_select = input('Enter choice: ')
# if image_select == '1':
    # print(f'saos-06-20-00-0211 selected')
    # image_file = 'saos-06-20-00-0211'
# elif image_select == '2':
    # print(f'saos-06-16-00-0265 selected')
    # image_file = 'saos-06-16-00-0265'
# else:
    # print(f'did not select 1 or 2. default to saos-06-20-00-0211')
    # image_file = 'saos-06-20-00-0211'
    
# Get input file with devices to work on
input_try = 0
hostfilepath = 'input_files/'
while input_try <= 2:
    hostfile = input('Enter Hostfile: ')
    if os.path.isfile(hostfilepath+hostfile):
        # print(f'\nFile to be used: {hostfile}\n')
        break
    else:
        print(f'File {hostfile} not found. try again\n')
        input_try += 1

if input_try == 3:
    sys.exit('Too many Tries. exiting script')

#Dry RUN. Default YES, meaning NO upgrade will be initiated
print('''
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
initiate upgrade or Dry_run? (Default is Dry run)
Enter Yes to start upgrading.
Enter No for Dry Run, no upgrade will be initiated.
''')

choice_dry_run = input('Enter choice: ')
if re.search('[yY]es',choice_dry_run):
    choice_dry_run = False
    print('Dry Run: No')
elif re.search('[nN]o',choice_dry_run):
    choice_dry_run = True
    print('Dry Run: Yes')
else:
    print(f'Nothing entered, default to Dry_run')
    choice_dry_run = True
print('@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n')
    
#Create log folder in current folder to store log files
if not os.path.exists('logs'):
    os.makedirs('logs')

hostlist = []
hostlistfile = open(hostfilepath+hostfile,'r')

for host in hostlistfile:
    host = host.strip()
    hostlist.append(host.strip()) 

max_input_count = 0
while True:
    max_fail = (input('Enter max device failures between 0 and 9 (default = 2): '))
    if max_fail == '':
        print('nothing entered. set max fail to 2')
        max_fail = 2
        break
    elif re.search('[0-9]',max_fail):
        print(f'Max fail set to {max_fail}')
        max_fail = int(max_fail)
        break
    else:
        if max_input_count < 3:
            print('No valid character entered. please try again')
            max_input_count += 1
        else:
            sys.exit('Too many wrong inputs, exiting script')

print(f'Software version to upgrade to: {image_file}')
            

  
errors = 0
fail_count = 0
failed_hosts = []
logfile = f'logs/{hostfile}_upgrade_{currenttime}.log'
log = open(logfile,'a')
log.write(f'''
@@@@@@@@@@@@@@@@@@@@@@@@@ Summary @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
Upgrade of SAOS6 devices to: {image_file}\n

Script started by: {username}

date: {currenttime}

input file used: {hostfile}

logfile: {logfile}

number of switches to upgrade : {len(hostlist)}

max switches allowed to fail before script stops: {max_fail}

log files used in this script:

- logfile: logs/{hostfile}_{currenttime}.log
- for each host:
    f'logs/{hostfile}_<host>_pre-config_{currenttime}.log
    f'logs/{hostfile}_<host>_pre-check_{currenttime}.log
    f'logs/{hostfile}_<host>_post-config_{currenttime}.log
    f'logs/{hostfile}_<host>_post-check_{currenttime}.log

''')
print(f'''
@@@@@@@@@@@@@@@@@@@@@@@@@ Summary @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
Upgrade of SAOS6 devices to: {image_file}\n

Script started by: {username}

date: {currenttime}

input file used: {hostfile}

logfile: {logfile}

number of switches to upgrade : {len(hostlist)}

max switches allowed to fail before script stops: {max_fail}

log files used in this script:

- logfile: logs/{hostfile}_{currenttime}.log
- for each host:
    logs/{hostfile}_<host>_pre-config_{currenttime}.log
    logs/{hostfile}_<host>_pre-check_{currenttime}.log
    logs/{hostfile}_<host>_post-config_{currenttime}.log
    logs/{hostfile}_<host>_post-check_{currenttime}.log

''')
    
if choice_dry_run:
    log.write('Dry run selected. Upgrade will NOT be initiated!!\n')
    print('################################################################\n')
    print('Dry run selected. Upgrade will NOT be initiated!!\n')
    print('################################################################\n')
else:
    log.write('Dry run not selected. Upgrade WILL be initiated!!!!\n')
    print('################################################################\n')
    print('Dry run not selected. Upgrade WILL be initiated!!!!\n')
    print('################################################################\n')
log.write('\n@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n')
print('\n@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n')
log.close()

go_no_go =  input('Press enter to continue, or any other character to end script.')
if go_no_go == '':
    pass
elif go_no_go == '\r':
    pass
else:
    sys.exit('Ending script')

ring_fail = 0
#MAIN SCRIPT
for host in hostlist:
    log = open(logfile,'a')
    if fail_count <= max_fail and ring_fail == 0:
        host = host.strip()
        # Login
        print(f'{host}: Connecting')
        log.write(f'{host}: Connecting\n')
        ssh_session, ssh_status = ssh_connection(host)
        if ssh_status:
            print(f'{host}: Connected')
            log.write(f'{host}: Connected\n')
            #CHECK IF SAOS6 DEVICE
            saos_version, current_saos = check_saos6(ssh_session)
            if saos_version and current_saos != image_file:
                print(f'{host}: is saos6 device. Running incorrect version({current_saos})')
                log.write(f'{host}: is saos6 device. Running incorrect version({current_saos})\n')
                #Gather facts PRE upgrade
                print(f'{host}: Starting PRE-Checks.')
                log.write(f'{host}: Starting PRE-Checks.\n')
                host_check_pre_file = f'logs/{hostfile}_{host}_pre-check_{currenttime}.log'
                host_check_pre = open(host_check_pre_file,'a')
                host_config_pre_file = f'logs/{hostfile}_{host}_pre-config_{currenttime}.cfg'
                host_config_pre = open(host_config_pre_file,'a')
                power_pre, power_red_pre = power_module(ssh_session)
                mac_table_pre = mac_table(ssh_session)
                ring_info_pre = get_ring_info(ssh_session)
                agg_status_pre = agg_state(ssh_session)
                port_status_pre = port_state(ssh_session)
                config_pre = get_config(ssh_session)
                ring_state_pre_state,ring_state_pre_get, ring_state_pre_info  = ring_state(ssh_session)
                host_check_pre.write(mac_table_pre + '\n')
                host_check_pre.write(ring_info_pre + '\n')
                host_check_pre.write(ring_state_pre_get + '\n')
                host_check_pre.write(agg_status_pre + '\n')
                host_check_pre.write(port_status_pre + '\n')
                host_check_pre.write(power_pre + '\n')
                host_check_pre.close()
                host_config_pre.write(config_pre)
                host_config_pre.close()
                print(f'{host}: Finished PRE-Checks.')
                log.write(f'{host}: Finished PRE-Checks.\n')
                #Check id switch is ready for upgrade
                #Check power supply and warn if one is missing
                if power_pre == 'Not Ok':
                    print(f'{host}: Power Warning!!!!! {power_red_pre}!')
                    log.write(f'{host}: Power Warning!!!!! {power_red_pre}!\n')                     
                #continue only if ring state is ok
                if ring_state_pre_state:
                    if 'No ring configured on device' in ring_state_pre_get:
                        print(f'{host}: No ring configured on device.')
                        log.write(f'{host}: No ring configured on device.\n')
                    else:
                        print(f'{host}: Ring protection pre state Ok.')
                        log.write(f'{host}: Ring protection pre state Ok.\n')
                    #Switch will start downloading and reboot without warning, so we check if session is gone. on average the proces lasts 180 seconds.
                    if choice_dry_run:
                        print(f'{host}: ########  Dry Run selected. not starting the upgrade!!!!##############')
                        #ssh_session.disconnect()
                        time.sleep(10)
                    else:
                        print(f'{host}: starting the upgrade. This can take a while and includes reboot')
                        upgrade_switch(ssh_session,image_file,host)
                        print(f'{host}: Waiting 180 seconds to allow for image download and upgrade.')
                        log.write(f'{host}: Waiting 180 seconds to allow for image download and upgrade.\n')
                        time.sleep(180)
                        #Check if session is gone
                        if ssh_session.is_alive():
                            #Session is still active, wait another 60 seconds
                            print(f'{host}: Still in progress, waiting another 60 seconds.')
                            log.write(f'{host}: Still in progress, waiting another 60 seconds.\n')
                            time.sleep(60)
                        else:
                            #Session is terminated
                            pass
                        print(f'{host}: Rebooting. waiting for 180 seconds to try to reconnect.')
                        log.write(f'{host}: Rebooting. waiting for 180 seconds to try to reconnect.\n')
                        #Wait 180 seconds for switch to come back online
                        time.sleep(180)
                        #Let`s try to login
                        print(f'{host}: Trying to connect.')
                        log.write(f'{host}: Trying to connect.\n')
                        ssh_session, ssh_status = ssh_connection(host)
                        if not ssh_status:
                            print(f'{host}: not back yet. waiting another 60 seconds')
                            log.write(f'{host}: not back yet. waiting another 60 seconds\n')
                            #Switch not back online yet, wait another 60 seconds
                            time.sleep(60)
                            ssh_session, ssh_status = ssh_connection(host)
                            if not ssh_status:
                                #Switch not back online yet, wait another 60 seconds
                                time.sleep(60)
                                ssh_session, ssh_status = ssh_connection(host)
                                if not ssh_status:
                                    ################################################################ADD FAILURE COUNT
                                    print(f'{host},failed to connect after upgrade')
                                    log.write(f'{host},failed to connect after upgrade\n')
                                    failed_hosts.append(f'{host},failed to connect after upgrade')
                                    errors += 1
                                    continue
                    if ssh_status:
                        #Switch back online, starting post checks
                        ##Gather facts POST upgrade
                        print(f'{host}: Starting POST-Checks.')
                        log.write(f'{host}: Starting POST-Checks.\n')
                        host_check_post_file = f'logs/{hostfile}_{host}_post-check_{currenttime}.log'
                        host_check_post = open(host_check_post_file,'a')
                        host_config_post_file = f'logs/{hostfile}_{host}_post-config_{currenttime}.cfg'
                        host_config_post = open(host_config_post_file,'a')
                        mac_table_post = mac_table(ssh_session)
                        power_post, power_red_post = power_module(ssh_session)
                        ring_info_post = get_ring_info(ssh_session)
                        agg_status_post = agg_state(ssh_session)
                        port_status_post = port_state(ssh_session)
                        config_post = get_config(ssh_session)
                        #Check RING STATE
                        ring_state_post_state,ring_state_post_get, ring_state_post_info  = ring_state(ssh_session)
                        if ring_state_post_state:
                            if 'No ring configured on device' in ring_state_post_get:
                                print(f'{host}: No ring configured on device.')
                                log.write(f'{host}: No ring configured on device.\n')
                            else:
                                print(f'{host}: Ring protection post state Ok')
                                log.write(f'{host}: Ring protection post state Ok\n')
                        else:
                            if 'Recovering' in ring_state_post_info:
                                print(f'{host}: Ring protection post state Recovering. waiting 6 minutes to wait for recovery')
                                log.write(f'{host}: Ring protection post state Recovering. waiting 6 minutes to wait for recovery\n')
                                time.sleep(360)
                                print(f'{host}: Checking ring state.')
                                log.write(f'{host}: Checking ring state.\n')
                                ring_state_post_state,ring_state_post_get, ring_state_post_info  = ring_state(ssh_session)
                                if 'Ok' in ring_state_post_info:
                                    print(f'{host}: Ring protection post state Ok')
                                    log.write(f'{host}: Ring protection post state Ok\n')
                                else:
                                    #Wait another 2 minutes
                                    print(f'{host}: Still recovering. waiting extra 2 minutes')
                                    log.write(f'{host}: Still recovering. waiting extra 2 minutes\n')
                                    time.sleep(120)
                                    print(f'{host}: Checking ring state again.')
                                    log.write(f'{host}: Checking ring state again.\n')
                                    if 'Ok' in ring_state_post_info:
                                        print(f'{host}: Ring protection post state Ok')
                                        log.write(f'{host}: Ring protection post state Ok\n')
                                    else:
                                        print(f'{host}: Ring protection post state NOT ok in pre and post check. state pre: {ring_state_pre_info}, state post : {ring_state_post_info}')
                                        log.write(f'{host}: Ring protection post state NOT ok in pre and post check. state pre: {ring_state_pre_info}, state post : {ring_state_post_info}\n')
                                        errors += 1
                                        ring_fail +=1
                                        failed_hosts.append(f'{host}: Ring protection post state NOT ok in pre and post check. state pre: {ring_state_pre_info}, state post : {ring_state_post_info}')
                            elif 'Protecting' in ring_state_post_info:
                                print(f'{host}: Ring protection post state NOT ok in pre and post check. state pre: {ring_state_pre_info}, state post : {ring_state_post_info}')
                                log.write(f'{host}: Ring protection post state NOT ok in pre and post check. state pre: {ring_state_pre_info}, state post : {ring_state_post_info}\n')
                                ring_fail +=1
                                errors += 1
                                failed_hosts.append(f'{host}: Ring state post: {ring_state_post_info}\n')
                            else:
                                print(f'{host}: Ring error.')
                                log.write(f'{host}: Ring error.')
                                ring_fail +=1
                                errors += 1
                                failed_hosts.append(f'{host}: Ring error')
                        host_check_post.write(mac_table_post + '\n')
                        host_check_post.write(ring_info_post + '\n')
                        host_check_post.write(ring_state_post_get + '\n')
                        host_check_post.write(agg_status_post + '\n')
                        host_check_post.write(port_status_post + '\n')
                        host_check_post.write(power_post + '\n')
                        host_check_post.close()
                        host_config_post.write(config_pre)
                        host_config_post.close()
                        print(f'{host}: Finished POST-Checks.')
                        log.write(f'{host}: Finished POST-Checks.\n')
                        #DO CHECKS TO VALIDATE
                        #Check power supply and warn if one is missing
                        if power_post == 'Not Ok':
                            print(f'{host}: Power Warning!!!!! {power_red_post}!')
                            log.write(f'{host}: Power Warning!!!!! {power_red_post}!\n')
                        #Check configs pre and post
                        print(f'{host}: Validating PRE and POST configs.')
                        log.write(f'{host}: Validating PRE and POST configs.\n')
                        config_diff, diff_config = compare_pre_post_config(host_config_pre_file,host_config_post_file)
                        if config_diff:
                            print(f'{host}: Configurations Pre and Post are equal.')
                            log.write(f'{host}: Configurations Pre and Post are equal.\n')
                        else:
                            print(f'{host}: Configurations Pre and Post configs are NOT equal. CHECK')
                            log.write(f'{host}: Configurations Pre and Post configs are NOT equal. CHECK\n')
                            for lines in diff_config:
                                print(f'{host}: {lines.strip()}')
                                log.write(f'{host}: {lines.strip()}\n')
                                errors += 1
                            failed_hosts.append(f'{host}: Configurations Pre and Post are NOT equal.')
                        #Check PRE and POS states
                        print(f'{host}: Validating PRE and POST checks.')
                        log.write(f'{host}: Validating PRE and POST checks.\n')
                        #Check port state pre and post
                        port_diff,port_diff_status  = compare_pre_post_config_port(host_check_pre_file,host_check_post_file)
                        if not port_diff_status:
                            errors += 1
                            failed_hosts.append(f'{host}: portstatus NOT equal')
                            print(f'{host}:portstatus NOT equal!!!!!!!')
                            log.write(f'{host}: portstatus NOT equal!!!!!!!\n')
                            for port in port_diff:
                                print(f'{host}: {port}')
                                log.write(f'{host}: {port}\n')
                        else:
                            print(f'{host}: All ports in same state before and after')
                            log.write(f'{host}: All ports in same state before and after\n')
                        #Check PRE and POST MAC table
                        mac_diff, mac_diff_status  = compare_mac(mac_table_pre,mac_table_post)
                        if not mac_diff_status:
                            print(f'{host}: mac_table NOT equal! Showing diff only')
                            log.write(f'{host}: mac_table NOT equal! Showing diff only\n')
                            for mac in mac_diff:
                                print(f'{host}: {mac}')
                                log.write(f'{host}: {mac}\n')
                        elif mac_diff_status:
                            print(f'{host}: mac_table pre - post equal!!!!!!!')
                            log.write(f'{host}: mac_table pre - post equal!!!!!!!\n')
                        
                        if config_diff and port_diff_status and ring_state_post_state:
                        #IF OK, cleanup
                            #ssh_session.send_command('software protect')
                            #CLEANUP AND SAVE CONFIG
                            print(f'{host}: Cleanup and saving config.')
                            log.write(f'{host}: Cleanup and saving config.\n')
                            clean_up(ssh_session)
                            print(f'{host}: upgrade succesfull. Don`t forget to protect software!')
                            log.write(f'{host}: upgrade succesfull. Don`t forget to protect software!\n')
                        else:
                            print(f'{host}: PRE-POST compare failed. Check issue')
                            log.write(f'{host}: PRE-POST compare failed. Check issue\n')
                            errors += 1
                            failed_hosts.append(f'{host}: PRE-POST compare failed')
                        #Combine all errors and increment fail_count with one. this counts as one device failure
                        if errors > 0:
                            fail_count += 1
                    else:
                        print(f'{host}: FAILED')
                        log.write(f'{host}: FAILED\n')
                else:
                    print(f'{host}: Not all rings in OK state. state: "{ring_state_pre_info}". skipping upgrade')
                    log.write(f'{host}: Not all rings in OK state. state: "{ring_state_pre_info}". skipping upgrade')
                    failed_hosts.append(f'{host}: Ring_Pre_state_not_ok({ring_state_pre_info})')
                    
            elif saos_version and current_saos == image_file :
                print(f'{host}: is saos6 device. already running correct version({current_saos})')
                log.write(f'{host}: is saos6 device. already running correct version({current_saos})\n')
            else:
                print(f'{host} is NOT saos6 device. Skipping')
                log.write(f'{host} is NOT saos6 device. Skipping\n')
            ssh_session.disconnect()
            print(f'{host}: Finished')
            log.write(f'{host}: Finished\n') 
        else:
            print(f'{host}: Failed to connect pre upgrade')
            log.write(f'{host}: Failed to connect pre upgrade\n')
            failed_hosts.append(f'{host}: Failed to connect pre upgrade')
    elif fail_count == max_fail:
        print('Reached max failed upgrades. stopping script')
        log.write('Reached max failed upgrades. stopping script\n')
    elif ring_fail == 1:
        print('Ring not recovered, ending script')
        log.write('Ring not recovered, ending script')
        # print(f'Hosts failed:')
        # log.write(f'Hosts failed:\n')        
        # for host in failed_hosts:
            # print(host)
            # log.write(Hosts) 
        break
    log.close()

log = open(logfile,'a')
print('\n########Failed hosts:###########')
log.write('\n########Failed hosts:###########\n')
if len(failed_hosts) > 0:
    for line in failed_hosts:
        print(line)
        log.write(f'{line}\n')
else:
    print('No failed hosts')
    log.write('No failed hosts\n')
print('\n#################################')
log.write('\n#################################\n')

log.write('''
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
    Don`t forget to protect software
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
''')
    
print('''
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
    Don`t forget to protect software
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
''')
    
print('\nEnd of script')
log.write('\nEnd of script\n')
log.close()
