import os
import re
import subprocess
import getopt, sys
from collections import Counter
from itertools import islice
from datetime import datetime
import pandas as pd

argv = sys.argv[1:]
devcenter = ''
subscriptions = ''

def displayHelp():
  print('python devbox-usage-report.py -d <devcenter> -s <subscriptions>')
  print('for example: python devbox-usage-report.py -d devcenter1 -s subscription1')
  print('for example: python devbox-usage-report.py -s subscription1,subscription2')
  return

try:
  opts, args = getopt.getopt(argv,"hd:s:",["devcenter=","subscriptions="])
except getopt.GetoptError:
  displayHelp()
  sys.exit(2)
for opt, arg in opts:
  if opt == '-h':
    displayHelp()
    sys.exit()
  elif opt in ("-d", "--devcenter"):
    devcenter = arg.strip()
  elif opt in ("-s", "--subscriptions"):
    subscriptions = arg.strip()
  else:
    displayHelp()
    sys.exit()
print('devcenter: ', devcenter)
print('subscriptions: ', subscriptions)

def removeTempFile(fileName):
  if os.path.exists(fileName):
      os.remove(fileName)
  else:
      print("The file {} does not exist".format(fileName))
  return

class DevBox():
  def __init__(self, name, actionState, powerState, poolName, project, devcenter, subscription, userId):
    self.name = name
    self.actionState = actionState
    self.powerState = powerState
    self.poolName = poolName
    self.project = project
    self.devcetner = devcenter
    self.subsription = subscription
    self.userId = userId

  def as_dict(self):
    return {'Subscription':self.subsription, 'DevCenter':self.devcetner, 'Project': self.project,'Dev Box Pool': self.poolName,'User Id':self.userId,'Running State':self.powerState}

class Developer():
  def __init__(self, displayName, principalName, userId):
    self.displayName = displayName
    self.principalName = principalName
    self.userId = userId

def getInfoByDevCenter(devcenter, subscription):
  tempFileName = 'devbox-info.txt'
  devboxCmd = "az devcenter dev dev-box list --dev-center-name " + devcenter + " -o table > " + tempFileName
  if subscription != "":
    devboxCmd = "az devcenter dev dev-box list --subscription "+ subscription +" --dev-center-name " + devcenter + " -o table > " + tempFileName
  
  #print(devboxCmd)
  os.system(devboxCmd)

  devboxInfoList = []
  with open(tempFileName,'r') as fileContent:
    for line in islice(fileContent,2,None):
      values = line.strip().split()
      if(len(values) >= 12):
        actionState = values[0]
        devboxName = values[4]
        poolName = values[6]
        powerState = values[7]
        projectName = values[8]
        userId = values[11]
        devbox = DevBox(devboxName,actionState,powerState,poolName,projectName,devcenter,subscription,userId)
        devboxInfoList.append(devbox)

  removeTempFile(tempFileName)
  return devboxInfoList

def getInfoBySubscription(subscription):
  # get the devcenter list under the subscription
  tempFileName = 'devcenter-info.txt'
  devboxCmd = "az devcenter admin devcenter list --subscription "+ subscription +" -o table > " + tempFileName
  #print(devboxCmd)
  os.system(devboxCmd)
  
  totalDeveloperList = Counter({})
  with open(tempFileName,'r') as fileContent:
    for line in islice(fileContent,2, None) :  # read from third line because first two lines are name and -----
      list = line.strip().split()
      devcetner = list[1].strip()
      if devcetner != "":
        developerList = getInfoByDevCenter(devcetner, subscription)
        totalDeveloperList += Counter(developerList)

  removeTempFile(tempFileName) 
  return totalDeveloperList

def getDeveloperInfo(userId):
  try:
    userInfo = ''
    if(sys.platform == 'win32'):
      userInfo = subprocess.check_output(['az','ad','user','show', '--id',userId],shell=True)
    else:
      userInfo = subprocess.check_output(["az ad user show --id " + userId],shell=True)
    displayNamePattern = b'displayName": "(.+)"'
    displayNameResult = re.search(displayNamePattern,userInfo)
    displayName = displayNameResult.group(1).decode("utf-8")

    userPrincipalNamePattern = b'userPrincipalName": "(.+)"'
    result = re.search(userPrincipalNamePattern,userInfo)
    userPrincipalName = result.group(1).decode("utf-8")

    developer = Developer(displayName, userPrincipalName, userId)
    return developer
  except:
    print("Cannot get the user info from the user id "+ userId)

def displayByDevcenter(developerList):
  
  GROUP_KEYS = ['Subscription','DevCenter','Project','Dev Box Pool','User Id']
  RUNNING_STATE = 'Running'
  RUNNING_STATE_COLUMN = 'Running State'
  USER_ID_COLUMN = 'User Id'
  COUNT_COLUMN = 'count'

  DISPLAY_RUNNING_COLUMN= 'Dev Box Count(Active)'
  DISPLAY_TOTAL_COLUMN = 'Dev Box Count(Total)'
  DISPLAY_USERNAME_COLUMN = 'User Name'
  DISPLAY_PRINCIPAL_NAME_COLUMN = 'User Principal Name'

  SNAPSHOT_TIME_COLUMN = 'Snapshot Time'

  snapshotTime = datetime.now()
  csvFile = 'result-' + snapshotTime.strftime("%Y-%m-%d-%H-%M-%S") +'.csv'

  # count by running state 
  df = pd.DataFrame([x.as_dict() for x in developerList])
  df_count = df.groupby(GROUP_KEYS)[RUNNING_STATE_COLUMN].value_counts().reset_index(name=COUNT_COLUMN)

  df_running = df_count[df_count[RUNNING_STATE_COLUMN] == RUNNING_STATE]
  df_not_running = df_count[df_count[RUNNING_STATE_COLUMN] != RUNNING_STATE]

  df_outer = pd.merge(df_running, df_not_running, how='outer', on=GROUP_KEYS).fillna(0).drop(columns=[RUNNING_STATE_COLUMN+'_x',RUNNING_STATE_COLUMN+'_y'])

  df_outer = df_outer.rename(columns={COUNT_COLUMN+'_x': DISPLAY_RUNNING_COLUMN, COUNT_COLUMN+'_y': DISPLAY_TOTAL_COLUMN})

  df_outer[DISPLAY_TOTAL_COLUMN] += df_outer[DISPLAY_RUNNING_COLUMN]
  df_outer[DISPLAY_RUNNING_COLUMN] = df_outer[DISPLAY_RUNNING_COLUMN].astype('int')
  df_outer[DISPLAY_TOTAL_COLUMN] = df_outer[DISPLAY_TOTAL_COLUMN].astype('int')  
  df_outer[SNAPSHOT_TIME_COLUMN] = snapshotTime.strftime("%Y-%m-%d %H:%M:%S")
  df_outer.insert(4, DISPLAY_USERNAME_COLUMN, None)
  df_outer.insert(5, DISPLAY_PRINCIPAL_NAME_COLUMN, None)
  
  for index, row in df_outer.iterrows():
    userId = row[USER_ID_COLUMN]
    developer = getDeveloperInfo(userId)
    if(developer is not None):
      df_outer.loc[index, DISPLAY_USERNAME_COLUMN] = developer.displayName
      df_outer.loc[index, DISPLAY_PRINCIPAL_NAME_COLUMN] = developer.principalName

  print(df_outer)
  df_outer.to_csv(csvFile,index=False)
  print("Scaning Completed!")
  return

if(subscriptions == "" and devcenter != ""):
  developerList = getInfoByDevCenter(devcenter,"")
  displayByDevcenter(developerList)
elif (subscriptions != "" and devcenter != ""):
  subscriptionList = subscriptions.split(',')
  totalDeveloperList = []
  for subscription in subscriptionList:
    developerList = getInfoByDevCenter(devcenter,subscription)
    totalDeveloperList.extend(developerList)
  displayByDevcenter(totalDeveloperList)
elif (subscriptions != "") and (devcenter == ""):
  subscriptionList = subscriptions.split(',')
  totalDeveloperList = []
  for subscription in subscriptionList:
    developerList = getInfoBySubscription(subscription)
    totalDeveloperList.extend(developerList)
  displayByDevcenter(totalDeveloperList)
else:
  displayHelp()

