import numpy as np
import math
import cv2

from tkinter import *
from tkinter import filedialog
from tkinter import messagebox
#import tkMessageBox

import pandas as pd

from path import Path
import glob, os, sys
import shutil

import json

import sys
import time



# this script is made for annotating and displaying quickly a photo database
# the mouse is there only to zoom in (right click) and zoom out (right click again) and move the image in zoom mode (drag with a left click)

# the rest is performed through keyboard shortcuts:
# L: load a photo folder (.jpg and .png files supported)
# n / right arrow: next file
# b / left arrow: previous file
# +: zoom in (in zoom mode only)
# -: zoom out (in zoom mode only)
# t: toggles on/off informations on screen (annotations, filter, zoom level)
# S: saves the annotation file (.csv file) - it is automatically loaded when present
# see function SetConfig for label types. With the default config, 3 labels are available:
# - ToDelete (d), red color
# - JpegOnly (j), orange color
# - BestOf (g), green color
# when pressing d, g or j it sets the corresponding label ON/OFF for the corresponding image
# when ON, a colored square is visible at the left side of the image
# when pressing D, G or J it enables or disables a filter based on the corresponding label.
# press one time: displays only photos WITH label ON
# press a second time: displays only photos WITHOUT label ON
# press a third time: disable the corresponding filter
# When enabled, a filter is displayed by a square contour on the left side of the image



root = Tk()



class PhotosDbAnnotate:


	def __init__(self):
		# set of Parameters

		# zooming utilities
		self.ZoomOn = False 	# this being false means that we're fitting the whole image into the view area
		self.ZoomRatio = 1.		# user determined by using + or - keys - by default it's a 100% crop
		self.InImageZoomCoords = (0,0)

		# dragging the zoomed area utilities
		self.DragFromCoords = (0,0)
		self.IsDragging = False
		self.StartingInImageCoords = (0,0)

		# current image matrices
		self.LoadedImg = []
		self.GlobalImg = []
		self.DisplayImg = []


		# exploration stuff
		self.PhotosFolder = ''
		self.FilesDataFrame = pd.DataFrame()
		#self.FilteredDF = pd.DataFrame()
		self.FilteredImgFileList = []
		self.CurrentListPosition = 0


		self.SetConfig()
		self.InitConfig()


		# general display stuff
		self.WindowSize = []
		self.BlankImage = np.zeros((self.DispH,self.DispW,3), np.uint8)
		#self.DispH, self.DispW, self.DispC = self.BlankImage.shape
		self.Offset = (0,0)
		self.DispRatio = 1.0
		self.DisplayAnnotations = True





	def SetConfig(self):

		# first: see if there's a config file to be loaded
		loaded = False

		if os.path.exists("./config.json"):
			#yes: load it
			with open("./config.json", 'r', encoding='utf-8') as json_file:
				try:
					data = json.load(json_file)

					reso = tuple(data['DisplayResolution'])
					self.DispW = reso[0]
					self.DispH = reso[1]

					self.RecordCsvFileName = str(data['RecordFileName'])

					self.LabelsList = data['LabelsList']

					#labelsDispConf = data['LabelsDisplay']

					self.LabelsSquaresWidth = data['LabelsDisplay']['SquaresWidth']
					self.LabelsSquaresVSpacing = data['LabelsDisplay']['SquaresVSpacing']
					self.LabelsSquaresThickness = data['LabelsDisplay']['Thickness']
					self.LabelsSquaresOuterBorderColor = data['LabelsDisplay']['OuterBorderColor']
					self.FilterSquaresOuterBorderColor = data['LabelsDisplay']['FilterOuterColor']

					loaded = True

				except:
					print("There was an issue loading the config file")


		if not loaded:
			self.SetDefaultConfig()





	def SetDefaultConfig(self):
		self.DispH=1200
		self.DispW=1800

		self.LabelsSquaresWidth = 30
		self.LabelsSquaresVSpacing = 20
		self.LabelsSquaresThickness = 2
		self.LabelsSquaresOuterBorderColor = (255,255,255)
		self.FilterSquaresOuterBorderColor = (  0,  0,  0)

		# define the labels
		self.LabelsList = []
		self.LabelsList.append({ 'Name': 'ToDelete', 'Key': 'd', 'Color': (  0,  0,255), 'Excludes': ['JpgOnly', 'BestOf'], 'Actions': [ 'CopyTo:ToDelete', 'ExtCopyTo::.ARW:ToDelete', 'DeleteRow' ] })
		self.LabelsList.append({ 'Name': 'JpgOnly',  'Key': 'j', 'Color': (  0,127,255), 'Excludes': ['ToDelete', 'BestOf'], 'Actions': [ 'ExtMoveTo::.ARW:ToDelete' ] })
		self.LabelsList.append({ 'Name': 'BestOf',   'Key': 'g', 'Color': ( 20,180, 20), 'Excludes': ['ToDelete', 'JpgOnly'], 'Actions': [ 'CopyTo:BestOf', 'ExtCopyTo::.ARW:BestOf' ] })

		self.RecordCsvFileName = "DbAnnotateRecord.csv"



		# possible actions:
		# MoveTo : RelPath
		# CopyTo : RelPath
		# ExtMoveTo : RelPathToExt : ReplacementExt : MoveTo
		# ExtCopyTo : ReplacementExt : RelPathToExt : RelPath


		#### the following lines are there to generate a 'config.json' file
		#### uncomment them when the configuration is changed
		if not os.path.exists('./config.json'):

			print("saving to config.json")

			SavingData = { 'DisplayResolution': (self.DispW, self.DispH),
						   'LabelsList': self.LabelsList,
						   'LabelsDisplay': {'SquaresWidth': self.LabelsSquaresWidth,
						   					 'SquaresVSpacing': self.LabelsSquaresVSpacing,
						   					 'Thickness': self.LabelsSquaresThickness,
						   					 'OuterBorderColor': self.LabelsSquaresOuterBorderColor,
						   					 'FilterOuterColor': self.FilterSquaresOuterBorderColor},
						   'RecordFileName': self.RecordCsvFileName }

			#print(SavingData)

			with open('config.json', 'w', encoding='utf-8') as f:
				json.dump(SavingData, f, indent=2)




	def InitConfig(self):
		# initialize the filter modes - set to 0 by default
		self.FilterMode = {}
		for i in range(0, len(self.LabelsList)):
			self.FilterMode[ self.LabelsList[i]['Name'] ] = 0

			# also computing the display rectangle positions

			RectDict = { 'LabelDisp':  (self.LabelsSquaresWidth, int(self.DispH/2)+i*(self.LabelsSquaresVSpacing+self.LabelsSquaresWidth),
										self.LabelsSquaresWidth, self.LabelsSquaresWidth),
			 			 'FilterDisp': (self.LabelsSquaresWidth-2*self.LabelsSquaresThickness, int(self.DispH/2)+i*(self.LabelsSquaresVSpacing+self.LabelsSquaresWidth)-2*self.LabelsSquaresThickness,
										self.LabelsSquaresWidth+4*self.LabelsSquaresThickness, self.LabelsSquaresWidth+4*self.LabelsSquaresThickness) }
			self.LabelsList[i] = dict(self.LabelsList[i], **RectDict)

		self.DBHasChanged = False

		# print("Filter Mode dict:")
		# print(self.FilterMode)

		# print("Labels dict list:")
		# print(self.LabelsList)






	def PerformActions(self):
		# so this is where we open a prompt and ask whether the user confirms performing the corresponding actions
		MsgBox = messagebox.askquestion ('Apply Annotations','Are you sure you want to apply the modifications?', icon = 'warning')
		if MsgBox != 'yes':
			return


		#DBHasChanged = False



		for ll in self.LabelsList:
			# first, get the list of files on which we want to perform actions and verify whether there's action to perform

			#print('Evaluating action :')
			#print(ll)

			if len(ll['Actions'])==0:
				# no point in doing anything if no action is required
				continue

			#print('... found some stuff to do')

			# determining the list of corresponding files
			filteredDF = self.FilesDataFrame[self.FilesDataFrame[ll['Name']]==True]


			#there's no point in going further if no file is concerned
			if len(filteredDF.index)==0:
				continue

			#print('... found corresponding data')

			listFilteredFiles = filteredDF['FileName'].tolist()

			#print(listFilteredFiles)


			for act in ll['Actions']:
				splitAct = act.split(":")

				ToFolder = ''

				action = splitAct[0]

				failuresList = []

				if action=='MoveTo' or action=='CopyTo' or action=='ExtMoveTo' or action=='ExtCopyTo':
					# verify if the folder exists, and if not, create it
					ToFolder = os.path.normpath( os.path.join(self.PhotosFolder, splitAct[-1]) )
					if not os.path.exists(ToFolder):
						os.makedirs(ToFolder)
						#print("created directory " + ToFolder)
						#if ToFolder[-1] != '/':
						#	ToFolder+= '/'

				rowsRemoveList = []

				for fil in listFilteredFiles:

					if fil in failuresList:
						#print("failure case detected: abandonning the line - " + fil)
						continue

					fileFrom = fil
					filWithExt = fil

					if action=='MoveTo' or action=='CopyTo':
						fileFrom = os.path.join(self.PhotosFolder, fil)
					elif action=='ExtMoveTo' or action=='ExtCopyTo':
						filWithExt = fileFrom[:fileFrom.rfind('.')]
						filWithExt = filWithExt + splitAct[2]
						fileFrom = os.path.join( os.path.normpath( os.path.join(self.PhotosFolder, splitAct[1]) ) , filWithExt )

					#print("from file name : " + fileFrom)

					fileTo = os.path.join( ToFolder, filWithExt )
					#print("to file name : " + fileTo)

					if not os.path.exists(fileFrom):
						failuresList.append(fil)
					else:
						if action=='MoveTo' or action=='ExtMoveTo':
							try:
								#print("moving file " + fileFrom + " to " + fileTo)
								shutil.move(fileFrom, fileTo)
							except:
								#print("failure on file " + fil)
								failuresList.append(fil)
						elif action=='CopyTo' or action=='ExtCopyTo':
							try:
								#print("copying file " + fileFrom + " to " + fileTo)
								shutil.copy(fileFrom, fileTo)
							except:
								#print("failure on file " + fil)
								failuresList.append(fil)

					if action == 'DeleteRow':
						tmpRemoveList = self.FilesDataFrame[self.FilesDataFrame['FileName'] == fil].index
						if len(tmpRemoveList)==1:
							rowsRemoveList.append(tmpRemoveList[0])
						else:
							print('wrong list length: ' + str(tmpRemoveList))

						# listIndicesToRemove = []
						# count = 0
						# for index, row in self.FilesDataFrame.iterrows():
						# 	if not os.path.exists(os.path.join(self.PhotosFolder, row['FileName'])):
						# 		listIndicesToRemove.append(index)
							#print(row['FileName'])
							#print(index)
						#	count += 1
						#	if count>10:
						#		break
						#print(listIndicesToRemove)

				#print("indices to remove : " + str(rowsRemoveList))
				if len(rowsRemoveList)>0:
					self.DBHasChanged = True

					self.FilesDataFrame = self.FilesDataFrame.drop(rowsRemoveList)

					# now we need to make indices start from 0 again
					self.FilesDataFrame = self.FilesDataFrame.reset_index(drop=True)



		if self.DBHasChanged:
			# then perform a reset
			self.ResetDisplay()





	def ResetDisplay(self):

		for i in range(0, len(self.LabelsList)):
			self.FilterMode[ self.LabelsList[i]['Name'] ] = 0

		self.FilteredImgFileList = self.FilesDataFrame['FileName'].tolist()

		self.CurrentListPosition = 0

		self.LoadImg()







	def HandleMouseClicks(self,event,x,y,flags,param):

		# the mouse is used mostly for the zooming functionnalities

		if event == cv2.EVENT_LBUTTONDOWN:
			# with the button pressed, we can move the visible area when the zoom is engaged
			#print("event button down")
			if self.ZoomOn:
				#print("beginning to move the zoomed in area")
				self.StartingInImageCoords = self.InImageZoomCoords
				self.DragFromCoords = (x,y)
				self.IsDragging = True

		if event == cv2.EVENT_MOUSEMOVE:
			# with the button pressed, we can move the visible area when the zoom is engaged
			#print("event button down")
			if self.ZoomOn and self.IsDragging:
				DeltaPos = (x-self.DragFromCoords[0], y-self.DragFromCoords[1])
				self.InImageZoomCoords = ( self.StartingInImageCoords[0] - int(DeltaPos[0]/self.ZoomRatio), self.StartingInImageCoords[1] - int(DeltaPos[1]/self.ZoomRatio) )
				self.RefreshImg()

		if event==cv2.EVENT_LBUTTONUP:
			# don't verify if we're already in zoom on mode
			self.IsDragging = False

			#print("ending the Dragging thing")


		if event == cv2.EVENT_RBUTTONDOWN:
			# switch from zoom mode enabled to zoom mode disabled

			self.ZoomOn = not self.ZoomOn

			if self.ZoomOn:
				# don't bother computing the zooming stuff if not necessary
				#print("Zoom on: " + str(self.ZoomOn))
				inImgZoomCoordsX = int((x-self.Offset[0])/self.DispRatio)
				inImgZoomCoordsY = int((y-self.Offset[1])/self.DispRatio)
				lH, lW, lC = self.LoadedImg.shape

				# okay but it would be better if we added an offset so that the point where we clicked stays at the same location once zommed in
				OffsetToCenterX = int((x-self.DispW/2)/self.ZoomRatio)
				OffsetToCenterY = int((y-self.DispH/2)/self.ZoomRatio)

				# ensure that we stay within the image boundaries
				self.InImageZoomCoords = ( min(lW, max(0,inImgZoomCoordsX-OffsetToCenterX)), min(lH, max(0,inImgZoomCoordsY-OffsetToCenterY)) )


			#print(self.InImageZoomCoords)
			self.RefreshImg()





	def LoadImg(self):
		# Do the redrawing pretty much all the time when there's a mouse action

		#global rectifyAnnotImg, orthoAnnotImg
		#img = np.zeros((512,512,3), np.uint8)
		#if len(self.FilteredDF.index)>self.CurrentListPosition:
		if len(self.FilteredImgFileList)>self.CurrentListPosition:
			#FileToLoad = self.FilteredDF.iloc[self.CurrentListPosition]['FileName']
			FileToLoad = self.FilteredImgFileList[self.CurrentListPosition]
			#print("trying to load file " + os.path.join(self.PhotosFolder, FileToLoad))
			start_time = time.time()
			self.LoadedImg = cv2.imread(os.path.join(self.PhotosFolder, FileToLoad))
			#print("--- image loading time: %s seconds ---" % (time.time() - start_time))

			self.ComputeGlobalImg()
			self.RefreshImg()
		else:
			# we cannot display anything actually (filtered too much or empty folder)
			# just display an empty image then
			self.LoadedImg = self.BlankImage.copy()






	def ComputeGlobalImg(self):

		if self.LoadedImg is not None :

			start_time = time.time()
			lH, lW, lC = self.LoadedImg.shape
			ratioW = self.DispW / lW
			ratioH = self.DispH / lH
			#print("ratios found: w=" + str(ratioW) + ", h=" + str(ratioH) )

			self.DispRatio = ratioW
			if ratioH<self.DispRatio:
				self.DispRatio = ratioH

			if self.DispRatio==1:
				self.GlobalImg = self.LoadedImg.copy()
			else:
				if self.DispRatio>1:
					# don't zoom on an image if it is smaller than the window - in this case we will center it
					self.DispRatio=1

				DispSize = (int(lW*self.DispRatio), int(lH*self.DispRatio))

				if DispSize[0]==self.DispW and DispSize[1]==self.DispH:
					# the simplest case: both dimensions match exactly the display window
					self.GlobalImg = cv2.resize(self.LoadedImg, DispSize, interpolation = cv2.INTER_CUBIC)
					# don't forget to specify that there's no offset here
					self.Offset = (0,0)
				else:
					# we have to fill the blanks with 0 values
					# first create a black image of right size
					self.GlobalImg = np.zeros((self.DispH, self.DispW, 3), np.uint8)
					# calculate the offset so that it is centered
					self.Offset = ( int( (self.DispW-DispSize[0]) / 2 ), int( (self.DispH-DispSize[1]) / 2 ) )
					#print("offset value : " + str(self.Offset))
					# fill the corresponding rectangle
					self.GlobalImg[self.Offset[1]:self.Offset[1]+DispSize[1],self.Offset[0]:self.Offset[0]+DispSize[0],:] = cv2.resize(self.LoadedImg, DispSize, interpolation = cv2.INTER_CUBIC)

			#print("--- global image redim and copying time: %s seconds ---" % (time.time() - start_time))
		

		else:
			# there was some issue. Just display a blank image then
			self.GlobalImg = np.zeros((self.DispH, self.DispW, 3), np.uint8)






	def RefreshImg(self):
		# do stuff to refresh img in function of the zoom or other stuff such as window size, etc
		if (not self.ZoomOn) and (self.GlobalImg is not None):
			# general view - just displaying the image we already computed
			self.DisplayImg = self.GlobalImg.copy()


		elif self.ZoomOn:
			start_time = time.time()

			# first check if the coordinates passed are within the image area (a bad situation may happen when we switch image)
			lH, lW, lC = self.LoadedImg.shape
			self.InImageZoomCoords = ( min(lW, max(0,self.InImageZoomCoords[0])), min(lH, max(0,self.InImageZoomCoords[1])) )

			# trying to bring the point where the user clicked as close as possible to the center of the display window
			# imagine we don't reach the boundaries of the original image, the coordinates within the original image would be as follows:
			IdealBoundaryTL = (self.InImageZoomCoords[0]-int(self.DispW/(2*self.ZoomRatio)), self.InImageZoomCoords[1]-int(self.DispH/(2*self.ZoomRatio)))
			IdealBoundaryBR = (self.InImageZoomCoords[0]+int(self.DispW/(2*self.ZoomRatio)), self.InImageZoomCoords[1]+int(self.DispH/(2*self.ZoomRatio)))
		
			# now converting it into coordinates that correspond to both the original image and the display area
			OrigImgCropTL = (max(0, IdealBoundaryTL[0]), max(0, IdealBoundaryTL[1]))
			OrigImgCropBR = (min(lW,IdealBoundaryBR[0]), min(lH,IdealBoundaryBR[1]))

			DispImgCropTL = (-min(0, int(IdealBoundaryTL[0]*self.ZoomRatio)), -min(0, int(IdealBoundaryTL[1]*self.ZoomRatio)))
			# 0 if we were inside the original image, a positive value if we were outside
			DispImgCropBR = ( min(self.DispW, DispImgCropTL[0]+int(self.ZoomRatio * (OrigImgCropBR[0]-OrigImgCropTL[0]))), min(self.DispH, DispImgCropTL[1]+int(self.ZoomRatio * (OrigImgCropBR[1]-OrigImgCropTL[1]))) )
			# stay within the display area and compute in function of the displayed area

			# fill the area with zeros anyway
			self.DisplayImg = np.zeros((self.DispH, self.DispW, 3), np.uint8)

			if self.ZoomRatio==1:
				# a simple copy without any resizing
				self.DisplayImg[DispImgCropTL[1]:DispImgCropBR[1], DispImgCropTL[0]:DispImgCropBR[0], : ] = self.LoadedImg[OrigImgCropTL[1]:OrigImgCropBR[1], OrigImgCropTL[0]:OrigImgCropBR[0], :].copy()
			else:
				# add the resizing stuff and it's a mess :)
				DispSize = (DispImgCropBR[0]-DispImgCropTL[0], DispImgCropBR[1]-DispImgCropTL[1])
				self.DisplayImg[DispImgCropTL[1]:DispImgCropBR[1], DispImgCropTL[0]:DispImgCropBR[0], : ] = cv2.resize(self.LoadedImg[OrigImgCropTL[1]:OrigImgCropBR[1], OrigImgCropTL[0]:OrigImgCropBR[0], :], DispSize, interpolation = cv2.INTER_CUBIC)

			if self.DisplayAnnotations:
				# draw a rectangle around the whole window to show that we're in zoom mode
				# Draw a rectangle with blue line borders of thickness of 2 px
				self.DisplayImg = cv2.rectangle(self.DisplayImg, (2,2), (self.DispW-2, self.DispH-2), (255, 0, 0), 4)
				self.DisplayImg = cv2.putText(self.DisplayImg, 'Zoom: '+str(int(self.ZoomRatio*100))+'%', (20,40), cv2.FONT_HERSHEY_COMPLEX, 1, (255, 0, 0), 2, cv2.LINE_AA)

			#print("--- zoom computation time: %s seconds ---" % (time.time() - start_time))
			
		else:
			self.DisplayImg = np.zeros((self.DispH, self.DispW, 3), np.uint8)


		if self.DisplayAnnotations:
			# display small 20x20 squares at the side of the image to show the annotations


			for ll in self.LabelsList:

				# display that a filter is activated or not
				if self.FilterMode[ll['Name']]>0:
					self.DisplayImg = cv2.rectangle(self.DisplayImg, ll['FilterDisp'], self.FilterSquaresOuterBorderColor, self.LabelsSquaresThickness*3)
					self.DisplayImg = cv2.rectangle(self.DisplayImg, ll['FilterDisp'], ll['Color'],  self.LabelsSquaresThickness)

			# displaying the image label only makes sense if there's an image to display
			if len(self.FilteredImgFileList)>0:
				# get the position in the whole dataframe
				correspondigDFPos = self.FilesDataFrame[self.FilesDataFrame['FileName'] == self.FilteredImgFileList[self.CurrentListPosition]].index[0]
				
				# display its information then
				for ll in self.LabelsList:
					if self.FilesDataFrame.iloc[correspondigDFPos][ll['Name']]:
						self.DisplayImg = cv2.rectangle(self.DisplayImg, ll['LabelDisp'], ll['Color'], -1)
						self.DisplayImg = cv2.rectangle(self.DisplayImg, ll['LabelDisp'], self.LabelsSquaresOuterBorderColor,  self.LabelsSquaresThickness)

			# also display where we're at in the queue
			self.DisplayImg = cv2.putText(self.DisplayImg, str(self.CurrentListPosition+1) + '/' + str(len(self.FilteredImgFileList)), (20,self.DispH-5), cv2.FONT_HERSHEY_COMPLEX, 1, (255, 0, 0), 2, cv2.LINE_AA)




		cv2.imshow('PhotoDisplay', self.DisplayImg)




	def LoadPhotosFolder(self, impath=''):
		#print("loading procedure")

		if len(impath)<1:
			if len(self.PhotosFolder)>1:
				self.PhotosFolder = filedialog.askdirectory(initialdir = self.PhotosFolder, title = "Select a Photo directory")
			else:
				self.PhotosFolder = filedialog.askdirectory(initialdir = "/", title = "Select a Photo directory")
		else:
			self.PhotosFolder = impath

		#if self.PhotosFolder[-1]!='/':
		#	self.PhotosFolder += '/'

		# clean the image list
		self.FilesDataFrame = pd.DataFrame()
		self.ListImgFiles = []
		self.FilteredImgFileList = []
		self.CurrentListPosition = 0
		self.ZoomOn = False



		if not os.path.exists(self.PhotosFolder):
			self.PhotosFolder = './'



		# see if there's a database file
		if os.path.exists(os.path.join(self.PhotosFolder, self.RecordCsvFileName)):

			# if so: simply load it
			self.FilesDataFrame = pd.read_csv(os.path.join(self.PhotosFolder, self.RecordCsvFileName))

			self.DBHasChanged = False

			# at this point we should verify if every line corresponds to a file and if every file corresponds to a line in the csv file
			# when a file doesn't exist: suppress the line
			# when a line doesn't exist, create it with false values
			# also: when a column is missing, create it and fill it with false values
			# conversely, suppress a column that is not in the config file
			# be careful with the sorting thing...
			self.CheckDFCompliance()


		else:

			#print("trying to load folder " + self.PhotosFolder)

			listFilenamesOnly = []

			for f in Path(self.PhotosFolder).walkfiles():
	    
				if not ((f.ext.lower()==".jpg") or (f.ext.lower()==".png")) :
					# just use the jpg or png extensions for now
					continue

				fileName = os.path.basename(f)

				if (fileName[0]=='.'):
					# avoid the annoying MacOs preview files
					continue

				if not os.path.exists(os.path.join(self.PhotosFolder, fileName)):
					# this is dumb, but this is the quick way i found to verify that we're within the parent folder
					continue

				newEntry = { 'FileName':fileName }#, 'ToDelete':False, 'JpgOnly':False, 'BestOf':False }
				# new entry: fill all the labels as False
				for ll in self.LabelsList:
					newEntry[ll['Name']] = False

				#self.FilesDataFrame = self.FilesDataFrame.append(newEntry, ignore_index=True)
				self.FilesDataFrame = pd.concat([self.FilesDataFrame, pd.DataFrame([newEntry])], ignore_index=True)

				#listFilenamesOnly.append(fileName)
				#print(fileName)

			#listFilenamesOnly = sorted(listFilenamesOnly)	#maybe rather put the sort in the Path thing
			# sort by filenames (for now, i may add the file date some day it's quite simple to do)
			self.FilesDataFrame = self.FilesDataFrame.sort_values(by=['FileName'])
			# reset the indexes so that they correspond to the row numbers - it makes the rest much easier
			self.FilesDataFrame = self.FilesDataFrame.reset_index(drop=True)

			# ensure that the boolean columns are in the right format and order
			#columnsSet = ['index', 'FileName']
			columnsSet = ['FileName']
			listlabs = []
			for ll in self.LabelsList:
				listlabs.append(ll['Name'])
				columnsSet.append(ll['Name'])
			#print(listlabs)

			# set the right type for the boolean columns
			#self.FilesDataFrame[['ToDelete','JpgOnly','BestOf']] = self.FilesDataFrame[['ToDelete','JpgOnly','BestOf']].astype('bool')
			self.FilesDataFrame[listlabs] = self.FilesDataFrame[listlabs].astype('bool')

			# putting the columns in the right order so that the csv is easier to read
			self.FilesDataFrame = self.FilesDataFrame[columnsSet]

			self.DBHasChanged = True


		# save the file list into a simple list, which is easier to manipulate
		self.FilteredImgFileList = self.FilesDataFrame['FileName'].tolist()


		#print(self.FilesDataFrame)

		self.LoadImg()



	def CheckDFCompliance(self):

		# first, set the columns list according to the config file

		# ensure that the boolean columns are in the right format and order
		#columnsSet = ['index', 'FileName']
		columnsSet = ['FileName']
		listlabs = []
		for ll in self.LabelsList:
			listlabs.append(ll['Name'])
			columnsSet.append(ll['Name'])

		# what we'll do now is compare the columns set of the config file to the column set from the dataframe
		dfList = self.FilesDataFrame.columns.tolist()
		#print('dfList : ' + str(dfList))

		dropList = []
		for dfl in dfList:
			if dfl not in columnsSet:
				dropList.append(dfl)

		if len(dropList)>0:
			# for now, we decide to respect strictly the config file and remove the corresponding columns
			# but we might opt otherwise and just LEAVE THEM ALONE ;(
			# maybe this is a parameter to add someday, although this should not be a recurring situation
			self.FilesDataFrame = self.FilesDataFrame.drop(columns=dropList)
			self.DBHasChanged = True


		# now more importantly, add columns when they're not there
		addList = []
		for cl in listlabs:
			if cl not in dfList:
				addList.append(cl)

		# fill them with False values
		if len(addList)>0:
			for al in addList:
				self.FilesDataFrame.insert(len(dfList)-len(dropList), al, False)
				self.DBHasChanged = True
				# update the columns length
				dfList.append(al)

			# ensure that the new columns are understood as boolean format
			self.FilesDataFrame[addList] = self.FilesDataFrame[addList].astype('bool')

		# finally put the columns in the right order
		self.FilesDataFrame = self.FilesDataFrame[columnsSet]


		# alright, so now we want to verify if all files still exist
		# we don't assume that any new file was created
		listIndicesToRemove = []
		count = 0
		for index, row in self.FilesDataFrame.iterrows():
			if not os.path.exists(os.path.join(self.PhotosFolder, row['FileName'])):
				listIndicesToRemove.append(index)
			#print(row['FileName'])
			#print(index)
		#	count += 1
		#	if count>10:
		#		break
		#print(listIndicesToRemove)
		if len(listIndicesToRemove)>0:
			self.FilesDataFrame = self.FilesDataFrame.drop(listIndicesToRemove)
			self.DBHasChanged = True

		# now we need to make indices start from 0 again
		self.FilesDataFrame = self.FilesDataFrame.reset_index(drop=True)


	# def saveResultsGUI(self):
	# 	print("saving procedure")

	# 	saveFilename = filedialog.asksaveasfilename(initialdir = "/", title = "Select file", filetypes = (("json files","*.json"),("all files","*.*")))
	# 	#saveFilename = '/Users/pierrelemaire/Documents/stationair/apps/code snippets/python homography calculator/test.json'


	# 	self.saveResults(saveFilename)

	def SaveDatabase(self):
		self.FilesDataFrame.to_csv(os.path.join(self.PhotosFolder, self.RecordCsvFileName), index=False)
		self.DBHasChanged = False



	def AskIfWeShouldSave(self):
		if self.DBHasChanged:
			MsgBox = messagebox.askquestion ('Save the Database?','Changes have been performed to the Database. Save?', icon = 'warning')
			if MsgBox == 'yes':
				self.SaveDatabase()
				return






	def loop(self):
		cv2.namedWindow('PhotoDisplay', cv2.WINDOW_NORMAL)
		#cv2.resizeWindow('PhotoDisplay', 3000, 2000)
		cv2.imshow('PhotoDisplay', self.BlankImage)

		#print(cv2.getWindowImageRect("PhotoDisplay"))
		cv2.setMouseCallback('PhotoDisplay', self.HandleMouseClicks)


		while(1):
			start_time = time.time()
			cv2.imshow('PhotoDisplay', self.DisplayImg)
			#print("--- image display time: %s seconds ---" % (time.time() - start_time))

			#if (len(self.WindowSize)==0):
				# first update
			#	self.RefreshWindowData()

			k = cv2.waitKey(0) & 0xFF
			if k == 27:
				# escape key
				#break
				if self.ZoomOn:
					self.ZoomOn = False
					self.RefreshImg()

			if k == ord('A'):
				self.PerformActions()

			if k == ord('Q'):
				self.AskIfWeShouldSave()
				break

			if k == ord('0'):
				self.ResetDisplay()

			elif k == ord('+') or k == ord('='):
				# this is quite stupid, but this forces values to be within boundaries
				# and i'm absolutely sure that i avoid any numerical error there
				if self.ZoomRatio==1:
					self.ZoomRatio=2
				elif self.ZoomRatio==2:
					self.ZoomRatio=4
				elif self.ZoomRatio==0.5:
					self.ZoomRatio=1
				elif self.ZoomRatio==0.25:
					self.ZoomRatio=0.5
				self.RefreshImg()

			elif k == ord('-'):
				# same as above
				if self.ZoomRatio==1:
					self.ZoomRatio=0.5
				elif self.ZoomRatio==2:
					self.ZoomRatio=1
				elif self.ZoomRatio==4:
					self.ZoomRatio=2
				elif self.ZoomRatio==0.5:
					self.ZoomRatio=0.25
				self.RefreshImg()

			elif k == ord('L'):
				# load another folder
				self.AskIfWeShouldSave()
				self.LoadPhotosFolder()


			elif k == ord('t'):
				# toggles the display of the attributes On and Off
				self.DisplayAnnotations = not self.DisplayAnnotations
				self.RefreshImg()

			elif (k == ord('n')) or (k == 3):
				# next image (in the filtered list)
				#self.CurrentListPosition = (self.CurrentListPosition + 1) % len(self.FilteredDF.index)
				self.CurrentListPosition = (self.CurrentListPosition + 1) % len(self.FilteredImgFileList)
				self.LoadImg()
				self.RefreshImg()

			elif (k == ord('b')) or (k == 2):
				# previous image (in the filtered list)
				#self.CurrentListPosition = (self.CurrentListPosition + (len(self.FilteredDF.index)-1)) % len(self.FilteredDF.index)
				self.CurrentListPosition = (self.CurrentListPosition + (len(self.FilteredImgFileList)-1)) % len(self.FilteredImgFileList)
				self.LoadImg()
				self.RefreshImg()

			elif (k == ord('S')):
				self.SaveDatabase()

			else:
				# the key pressed might correspond to a labelling or a filtering task
				for ll in self.LabelsList:

					if k == ord(ll['Key']):
						# switch label ON/OFF
						fn = self.FilteredImgFileList[self.CurrentListPosition]
						correspondigDFPos = self.FilesDataFrame[self.FilesDataFrame['FileName'] == fn].index[0]
						#val = self.FilteredDF.iloc[self.CurrentListPosition]['ToDelete']
						val = self.FilesDataFrame.iloc[correspondigDFPos][ll['Name']]
						self.FilesDataFrame.loc[(self.FilesDataFrame['FileName'] == fn), ll['Name']] = not val

						if len(ll['Excludes'])>0 and not val:
							# some exclusive rules have been formulated and we have set the image to be True in this category...
							for exclCat in ll['Excludes']:
								self.FilesDataFrame.loc[(self.FilesDataFrame['FileName'] == fn), exclCat] = False

						self.RefreshImg()

					elif k== ord(ll['Key'].upper()):
						# able / disable a filter
						# first: recording the current position
						CurrentFN = 0
						if len(self.FilteredImgFileList)>0:
							CurrentFN = self.FilteredImgFileList[self.CurrentListPosition]

						# second: copy the original list, which is unfiltered
						#self.FilteredDF = self.FilesDataFrame.copy(deep=False)

						# we perform a filter through the pandas thing
						filteredDF = self.FilesDataFrame.copy(deep=False)

						# if the list is empty, just skip the index and increase it
						for i in range(0,3):
							# keep the range contained so that we're certain to avoid an infinite loop, although this should be handled
							# set the filter toggle
							self.FilterMode[ll['Name']] = (self.FilterMode[ll['Name']] + 1) % 3
							#print("Filter mode value : " + str(self.FilterMode[ll['Name']]))

							# apply the corresponding filter when needed
							if (self.FilterMode[ll['Name']]==1):
								#self.FilteredDF = self.FilteredDF[self.FilteredDF['BestOf']==True].copy(deep=False)
								filteredDF = self.FilesDataFrame[self.FilesDataFrame[ll['Name']]==True]
							elif (self.FilterMode[ll['Name']]==2):
								filteredDF = self.FilesDataFrame[self.FilesDataFrame[ll['Name']]==False]
							else:
								filteredDF = self.FilesDataFrame.copy(deep=False)

							#print(filteredDF.index)
							if len(filteredDF.index)>0:
								break

						if self.FilterMode[ll['Name']] != 0:
							# if a filter was previously activated, we remove it
							for ll2 in self.LabelsList:
								if ll2['Name']!=ll['Name']:
									self.FilterMode[ll2['Name']] = 0


						#totalFileList = self.FilesDataFrame['FileName'].tolist()
						# keep the list of files to display as simple as possible
						self.FilteredImgFileList = filteredDF['FileName'].tolist()
						self.CurrentListPosition = 0

						if len(self.FilteredImgFileList)>0:	# this condition should be useless now

							# find the first next file in the list that corresponds to the filter
							PrevPos = 0
							if len(self.FilesDataFrame[self.FilesDataFrame['FileName'] == CurrentFN].index)>0:
								PrevPos = self.FilesDataFrame[self.FilesDataFrame['FileName'] == CurrentFN].index[0]

							indexList = filteredDF.index
							for self.CurrentListPosition in range(0, len(indexList)):
								if indexList[self.CurrentListPosition]>=PrevPos:
									break

						self.LoadImg()
						self.RefreshImg()
				#print(k)







if __name__ == '__main__':
	pda = PhotosDbAnnotate()
	#pda.LoadPhotosFolder('./')
	#pda.LoadPhotosFolder('/Users/pi/Documents/misc/polaroids/')
	pda.LoadPhotosFolder()
	pda.RefreshImg()
	pda.loop()




