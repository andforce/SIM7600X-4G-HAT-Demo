import SIM7600CE

'''
在第一次使用GPS时需要等待40秒左右，第二及以后只需要几秒即可
'''
time,location = SIM7600CE.get_gps_information()  #获取北京时间和当前位置

print("北京时间为："+time)
print("当前位置为："+location)

SIM7600CE.Send_Message("+8612345678901",location+time)  #将时间和位置发送到指定的手机号码