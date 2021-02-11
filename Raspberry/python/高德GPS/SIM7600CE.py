#!/usr/bin/python3
#_*_ coding:utf-8 _*_

import requests  #用于高德地图API请求
import json      #用于接收高德地图API反馈
import serial    #串口
import time
import queue     #队列
from datetime import timedelta   #日期和时间管理
from datetime import datetime

queue_list = queue.Queue(maxsize=20)       #实例化一个最大容纳20个任务的队列

final_GPSinfo = ''
Message = ''

ser = serial.Serial("/dev/ttyAMA0", 115200) #树莓派串口地址
ser.flushInput()                            #清空串口的输入

# AT指令备注
# AT_command_dictionary = {'Turn_on_gps_command'      :'AT+CGPS=1,1', #开启GPS，工作模式1
#                          'Get_gpsinfo_command'      :'AT+CGPSINFO', #获取GPS信息，
#                          'Turn_off_gps_command'     :'AT+CGPS=0',   #关闭GPS
#                          'Call_number'              :'ATD',         #ATD+传入的电话号码;
#                          'Hung_up'                  :'AT+CHUP',     #挂断电话
#                          'Answer_the_phone'         :'ATA',         #接听来电
#                          'set_Message_mode:text'    :'AT+CMGF=1',   #设置短信发送模式为1：模式  2：文本模式
#                          'set_Message_recive_number':'AT+CMGS=' ,
#                          'set_Message_service_center_number':'AT+CSCA=\"+8613010112500\"'#等号后填写目标电话号码，模块返回>后即可开始编写短信内同
#                          }



def Check_Sim7600():

    ser.write(('AT').encode())
    time.sleep(0.5)
    ser.write(('\r').encode())
    ser.write(('\r').encode())
    time.sleep(0.5)

    if ser.inWaiting():
        status=str(ser.read(ser.inWaiting()).decode())
        if "OK" in status:
            print("SIM7600初始化正常")
            return 1
        else:
            print("SIM7600初始化异常")
            return 0
    else:
        return 0
        print("SIM7600串口状态异常")

'''
打开GPS，冷启动需要等待大概30秒，如果期间未接收到GPS信息，会返回',,,,,,,,'，
因此此处使用循环检测返回信息的内容，直到出现包含'不包含',,,,,,,'且包含'OK'的内容时，结束循环，返回GPS信息
'''
def get_gps_information():

    try:
        flushserial()
        ser.write(('AT+CGPS=1,1'+'\r').encode())    #开启GPS
        print('GPS已经打开')
        time.sleep(2)
        flushserial()
        i = 20
        while True:
            ser.write(('AT+CGPSINFO' + '\r').encode()) #尝试获取GPS信息
            print('正在尝试获取 GPS 信息......')
            time.sleep(1)

            if ser.inWaiting():
                time.sleep(1)
                GPSinfo = str(ser.read(ser.inWaiting()).decode())
                # 这里简单的判断返回的字符串中的内容，来判断返回的信息是否有效
                if 'OK' in GPSinfo and ',,,,,,,,' not in GPSinfo:
                    print('成功获取GPS信息：\n')
                    print(GPSinfo)
                    break
                else:
                    time.sleep(3)
            else:
                time.sleep(3)
                i = i-1

            if i == 0:
                break
            else:
                continue

        GPSinfo = str(GPSinfo)

        N_or_S, W_or_E, UTC_Date_Time = convert_GPSinfo(GPSinfo)
        locationis = reverse_analysis(W_or_E, N_or_S)

        return UTC_Date_Time,locationis

        turn_off_GPS()

    except:
        turn_off_GPS()

'''
经测试稳定的发送中文短信的代码，简单流程，未对每一步的返回值进行判断
'''
def Send_Message(phonenumber,shortmessage):

    try:
        print("开始编辑短信")
        shortmessage_unicode = str_to_unicode(shortmessage) #调用方法将字符转化为对应的16进制UNICODE编码形式
        phonenumber_unicode = str_to_unicode(phonenumber)
        ser.write(("AT+CMGF=1"+'\r').encode()) #设置短信模式为1：TEXT模式，0：PDU模式（十分复杂的模式）
        time.sleep(0.5)
        ser.write(("AT+CSCS=\"UCS2\""+'\r').encode()) #设置短信采用UCS2编码
        time.sleep(0.5)
        ser.write(("AT+CSMP=17,167,2,25"+'\r').encode()) #设置短信编码、有效日期、返回状态等相关参数
        time.sleep(0.5)
        ser.write(("AT+CMGS="+"\""+phonenumber_unicode+"\""+"\r\n").encode()) #设置16进制UNICODE编码的接收方电话号码
        time.sleep(0.5)
        ser.write((shortmessage_unicode).encode()) #输入16进制UNICODE编码的短信内容
        time.sleep(0.5)
        ser.write(b'\x1A') #输入发送短信指令
        time.sleep(0.5)
        flushserial()  #清空串口，防止卡死
        print("短信发送成功")

    except:
        print("短信发送失败")
        return 0

'''
SIM7600发送中文需要使用UCS2编码，因此需要使用此方法将字符集转化为UCS2编码格式
UCS2为UNICODE编码的别称，本方法采用先将传入的字符转码为ASCII编码格式，
之后再将此格式由8位转化为16位，同时将原本输出的HEX(ASCII)码的'0X'去除
SIM7600最终将识别方法输出的字符编码。
使用此编码方式发送短信，可支持UNICODE所支持的一切字符集
'''
def str_to_unicode(str):
    str_format_unicode = ''
    for i in str:
        # 注意 upper函数处理是必须的，SIM7600不识别小写的UNICODE编码
        buff = hex(ord(i)).replace('0x', '').zfill(4).upper()
        str_format_unicode = str_format_unicode + buff

    return str_format_unicode

def flushserial():
    ser.flushOutput()
    ser.flushInput()

'''
先使用find_sign_index(',',GPSinfo)方法，得到包含全部','位置的列表
之后利用','的位置对，返回的GPS信息进行裁剪，并对经纬度，时间时区等进行换算

模块返回的GPSINFO：
# +CGPSINFO: 3939.241751,N,11608.941764,E,230420,090910.0,29.5,0.0,0.0
# OK

裁剪结果：
# 纬度： 39.654029183333336
# 经度： 116.1490294
# UTC日期： [20，4，23，9，9，10]
'''

def convert_GPSinfo(GPSinfo):
    comma_index = find_sign_index(',', GPSinfo)
    colon_index = GPSinfo.find(':')

    raw_N_or_S = GPSinfo[colon_index+2:comma_index[0]]
    raw_W_or_E = GPSinfo[comma_index[1]+1:comma_index[2]]

    raw_UTC_Date = GPSinfo[comma_index[3]+1:comma_index[4]]
    raw_UTC_Time = GPSinfo[comma_index[4]+1:comma_index[5]]

    raw_N_or_S_point_index = raw_N_or_S.find('.')
    raw_W_or_E_point_index = raw_W_or_E.find('.')

    N_or_S_int = raw_N_or_S[0:raw_N_or_S_point_index-2]
    N_or_S_float = raw_N_or_S[raw_N_or_S_point_index-2:len(raw_N_or_S)]
    W_or_E_int = raw_W_or_E[0:raw_W_or_E_point_index-2]
    W_or_E_float = raw_W_or_E[raw_W_or_E_point_index-2:len(raw_W_or_E)]
    N_or_S = str(int(N_or_S_int) + float(N_or_S_float)/60)
    W_or_E = str(int(W_or_E_int) + float(W_or_E_float)/60)

    UTC_Time = raw_UTC_Time[0:2] + ":" + raw_UTC_Time[2:4] + ":" + raw_UTC_Time[4:6]
    UTC_Date = "20" + raw_UTC_Date[4:6] + "-" + raw_UTC_Date[2:4] + "-" + raw_UTC_Date[0:2]

    UTC_Date_Time = UTC_Date + " " + UTC_Time
    UTC_Date_Time = Timezone_delay(UTC_Date_Time)

    print(N_or_S, W_or_E, UTC_Date_Time)

    return N_or_S, W_or_E, UTC_Date_Time

'''
此处使用了高德地图的WEB API对经纬度进行逆向解析，从而返回地址名称
'''

def reverse_analysis(W_or_E, N_or_S):
    try:
        print(W_or_E, N_or_S)
        url = 'https://restapi.amap.com/v3/geocode/regeo?' \
              'key=41b3b956352f82d8af8732824f91202f&location=%s,%s' \
              '&extensions=base'
        rawis = (W_or_E, N_or_S)
        res = requests.get(url % rawis)
        json_data = json.loads(res.text)
        return json_data['regeocode']['formatted_address']
    except:
        return 0

def Timezone_delay(UTC_Date_Time):
    utc_time = datetime.strptime(UTC_Date_Time, '%Y-%m-%d %H:%M:%S')
    Date_Time = utc_time + timedelta(hours=8)
    Date_Time = str(Date_Time)
    return Date_Time

'''
这里使用循环来到传入的字符串中查找指定字符的位置，并将所有查找到的字符的位置添加到列表中，
此外还使用try，except来退出循环，因为当运行到最后一次循环时，head_index后面已经没有指定的字符，
因此这一次的循环在执行到comma_index = content.index(char, head_index)时，
无法给comma_index返回一个合法的整数值，而使用try处理这个错误，就可以忽略最后一次的无效循环，
最终返回正确的、包含全部指定字符位置的列表
'''

def find_sign_index(char, content):
    index = []
    head_index = 0
    end_index = len(content)
    while (head_index <= end_index):
        try:
            comma_index = content.index(char, head_index)
            index.append(comma_index)
            head_index = comma_index + 1
        except:
            break
    return index

def turn_off_GPS():
    flushserial()
    ser.write(('AT+CGPS=0'+'\r').encode())
    time.sleep(1)
    flushserial()
    print('GPS 已经关闭')
