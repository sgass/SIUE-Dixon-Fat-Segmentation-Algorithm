import os.path
from pathlib import Path

import nibabel as nib
import numpy as np
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from lxml import etree
from configureWindow import ConfigureWindow
import skimage.exposure
import dicom2
import nrrd
import logging

import constants
import mainWindow_ui
from runSegmentation import runSegmentation


class MainWindow(QMainWindow, mainWindow_ui.Ui_MainWindow):
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.setupUi(self)

        self.sourceModel = QStandardItemModel(self.sourceListView)
        self.sourceListView.setModel(self.sourceModel)
        
        self.t1Series = []

        #Add options to dataTypeComboBox
        self.dataTypeComboBox.addItems(["Dixon Format","Wash U v1","Wash U v2"])

    @pyqtSlot()
    def on_browseSourceButton_clicked(self):
        pass
        # Read settings file
        settings = QSettings()
        
        # Get the default open path when starting the file dialog, default is the user's home directory
        defaultOpenPath = settings.value('defaultOpenPath', str(Path.home()))
        
        w = QFileDialog(self)
        w.setFileMode(QFileDialog.DirectoryOnly)
        w.setWindowTitle('Select source folders of subjects')
        w.setDirectory(defaultOpenPath)
        # Must use custom dialog if I want multiple directories to be selected
        w.setOption(QFileDialog.DontUseNativeDialog, True)
       
        # Custom command to allow for multiple directories to be selected
        for view in self.findChildren((QListView, QTreeView)):
            if isinstance(view.model(), QFileSystemModel):
                view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        
        # Start the dialog box and wait for input, it returns false if cancel was pressed
        if not w.exec():
            return
        
        # Get selected directories
        dirs = w.selectedFiles()
        
        # If empty, then cancel was pressed, return
        if not dirs:
            return
        
        # Since there were items selected, set the default open path to be the directory the user was last in
        # Save it to settings
        defaultOpenPath = w.directory().absolutePath()
        settings.setValue('defaultOpenPath', defaultOpenPath)
        
        # Check to make sure the directories are valid
        # Note: Don't use dir as variable name because it shadows built-in variable
        error = False
        for dir_ in dirs:
            if os.path.isdir(dir_):
                self.sourceModel.appendRow(QStandardItem(dir_))
            else:
                error = True
        
        # If an error occurred, tell the user that the directory was not added
        if error:
            QMessageBox.critical(self, "Invalid directory",
                                 "One of the directories you chose was invalid. It was not added to the list")

    @pyqtSlot()
    def on_runButton_clicked(self):
        # If there are no source files, then return
        # if self.sourceModel.rowCount() is 0:
        #     QMessageBox.warning(self, "No source directories",
        #                         "There are no source directories in the list currently. Please add some folders "
        #                         "before converting.")
        #     return

        #dataPath = "/home/somecallmekenny/SIUE-Dixon-Fat-Segmentation-Algorithm/Data/Subject0001_Final/"
        # Get selected index text
        selectedIndices = self.sourceListView.selectedIndexes()
        dataPath = selectedIndices[0].data()

        print('Beginning segmentation for ' + dataPath)


        # fatImage, waterImage, config = self.loadFile(dataPath)
        image, config = self.loadFile(dataPath)
        if image is None:
            print("No image")
            return

        # Set constant pathDir to be the current data path to allow writing/reading from the current directory
        constants.pathDir = dataPath

        # Run segmentation algorithm
        runSegmentation(image, config)

        print('Segmentation complete!')

    @pyqtSlot()
    def on_configureButton_clicked(self):
        selectedIndices = self.sourceListView.selectedIndexes()

        if self.sourceModel.rowCount() is 0:
            QMessageBox.warning(self, "No source directories",
                                "There are no source directories in the list currently. Please add some folders "
                                 "before converting.")
            return
        elif len(selectedIndices) == 0:
            QMessageBox.warning(self, "No selected source directories",
                                "There are no source directories selected currently. Please select one.")
            return
        elif len(selectedIndices) != 1:
            QMessageBox.warning(self, "Multiple selected directories",
                                 "There are currently more than one directories selected to configure. "
                                 "Please select only one.")
            return

        # Get selected index text
        dataPath = selectedIndices[0].data()
        #dataPath = "/home/somecallmekenny/SIUE-Dixon-Fat-Segmentation-Algorithm/Data/Subject0001_Final/"


        # Load data from path
        # Use Correct Load File function based on datatype
        DataTypeIndex = self.dataTypeComboBox.currentIndex() 
        if DataTypeIndex == 0:
            fatImage, waterImage, config = self.loadOldDixonFile(dataPath)
            self.configureWindow = ConfigureWindow(fatImage, waterImage, config, dataPath, parent=self)
        elif DataTypeIndex == 1:
            image, config = self.loadT1File(dataPath)
        else:
            QMessageBox.warning(self, "Problem With Data In dataTypeDropBox","Fix index issue.")
        #if image is None:
        #    return

        
        self.configureWindow.show()

    #This is for the T1 Data from WashU
    def loadT1File(self, dataPath):
        dicomDir = dataPath + "/SCANS/"
        print(dicomDir)
        # Load DICOM directory and organize by patients, studies, and series
        patients = dicom2.loadDirectory(dicomDir)
        # Should only be one patient so retrieve it
        patient = patients.only()
        # Should only be one study so retrieve the one study

        # doesn't work because of 35 studies
        # Double loop through studies then series (series is the images
        study = patient.only()
        #
        self.t1Series = []
        for UID, series in study.items():
            if series.Description.startswith('t1_'):
                self.t1Series.append(series)

        # Sort cine images by the series number, looks nicer
        self.t1Series.sort(key=lambda x: x.Number)

        # Loop through each t1 series
        for series in self.t1Series:
            seriesNumber = 21001
            sliceIndex = -1

            sortedSeries, _, _ = dicom2.sortSlices(series, dicom2.MethodType.Unknown)
            if sliceIndex < 0:
                continue
            elif sliceIndex >= len(sortedSeries):
                QMessageBox.critical(self, 'Invalid slice index', 'Invalid slice index given for series number %i'
                                     % seriesNumber)
                return

            print("Slices Sorted")

        (method, type_, space, orientation, spacing, origin, volume) = \
            dicom2.combineSlices(sortedSeries, method=dicom2.MethodType.Unknown)

        nrrdHeaderDict = {'space': space, 'space origin': origin,
                          'space directions': (np.identity(3) * np.array(spacing)).tolist()}
        nrrd.write(
            "/home/somecallmekenny/SIUE-Dixon-Fat-Segmentation-Algorithm/MRI_Data_Nrrd_Output/newOut.nrrd",
            volume, nrrdHeaderDict)
        constants.nrrdHeaderDict = {'space': 'right-anterior-superior'}

        configFilename = os.path.join(dataPath, 'config.xml')

        if not os.path.isfile(configFilename):
            print('Missing required files from source path folder. Continuing...')
            return None, None, None
        # Load config XML file
        config = etree.parse(configFilename)

        # Get the root of the config XML file
        configRoot = config.getroot()

        return volume, config

    #This is for the Dixon Format From Texas
    def loadOldDixonFile(self,dataPath):    
        # Get the filenames for the rectified NIFTI files for current dataPath
        niiFatUpperFilename = os.path.join(dataPath, 'fatUpper.nii')
        niiFatLowerFilename = os.path.join(dataPath, 'fatLower.nii')
        niiWaterUpperFilename = os.path.join(dataPath, 'waterUpper.nii')
        niiWaterLowerFilename = os.path.join(dataPath, 'waterLower.nii')
        configFilename = os.path.join(dataPath, 'config.xml')

        if not (os.path.isfile(niiFatUpperFilename) and os.path.isfile(niiFatLowerFilename) and os.path.isfile(
                niiWaterUpperFilename) and os.path.isfile(niiWaterLowerFilename) and os.path.isfile(
            configFilename)):
            print('Missing required files from source path folder. Continuing...')
            return None, None, None

        # Load unrectified NIFTI files for the current dataPath
        niiFatUpper = nib.load(niiFatUpperFilename)
        niiFatLower = nib.load(niiFatLowerFilename)
        niiWaterUpper = nib.load(niiWaterUpperFilename)
        niiWaterLower = nib.load(niiWaterLowerFilename)

        # Load config XML file
        config = etree.parse(configFilename)

        # Get the root of the config XML file
        configRoot = config.getroot()

        # Piece together upper and lower images for fat and water
        # Retrieve the inferior and superior axial slice from config file for upper and lower images
        imageUpperTag = configRoot.find('imageUpper')
        imageLowerTag = configRoot.find('imageLower')
        imageUpperInferiorSlice = int(imageUpperTag.attrib['inferiorSlice'])
        imageUpperSuperiorSlice = int(imageUpperTag.attrib['superiorSlice'])
        imageLowerInferiorSlice = int(imageLowerTag.attrib['inferiorSlice'])
        imageLowerSuperiorSlice = int(imageLowerTag.attrib['superiorSlice'])

        # Use inferior and superior axial slice to obtain the valid portion of the upper and lower fat and water images
        fatUpperImage = niiFatUpper.get_data()[:, :, imageUpperInferiorSlice:imageUpperSuperiorSlice]
        fatLowerImage = niiFatLower.get_data()[:, :, imageLowerInferiorSlice:imageLowerSuperiorSlice]
        waterUpperImage = niiWaterUpper.get_data()[:, :, imageUpperInferiorSlice:imageUpperSuperiorSlice]
        waterLowerImage = niiWaterLower.get_data()[:, :, imageLowerInferiorSlice:imageLowerSuperiorSlice]

        # Concatenate the lower and upper image into one along the Z dimension
        # TODO Consider removing this and performing segmentation on upper/lower pieces separately
        fatImage = np.concatenate((fatLowerImage, fatUpperImage), axis=2)
        waterImage = np.concatenate((waterLowerImage, waterUpperImage), axis=2)

        # Normalize the fat/water images so that the intensities are between (0.0, 1.0)
        # Also converts to float data type
        fatImage = skimage.exposure.rescale_intensity(fatImage.astype(float), out_range=(0.0, 1.0))
        waterImage = skimage.exposure.rescale_intensity(waterImage.astype(float), out_range=(0.0, 1.0))

        # Set constant pathDir to be the current data path to allow writing/reading from the current directory
        constants.pathDir = dataPath

        constants.nrrdHeaderDict = {'space': 'right-anterior-superior'}
        constants.nrrdHeaderDict['space directions'] = (niiFatUpper.header['srow_x'][0:-1],
                                                        niiFatUpper.header['srow_y'][0:-1],
                                                        niiFatUpper.header['srow_z'][0:-1])

        constants.nrrdHeaderDict['space origin'] = (niiFatUpper.header['srow_x'][-1],
                                                    niiFatUpper.header['srow_y'][-1],
                                                    niiFatUpper.header['srow_z'][-1])

        return fatImage, waterImage, config
        
    ###OLD MAIN WINDOW###
    # import os.path
    # from pathlib import Path
    #
    # import nibabel as nib
    # import numpy as np
    # from PyQt5.QtCore import *
    # from PyQt5.QtGui import *
    # from PyQt5.QtWidgets import *
    # from lxml import etree
    # from configureWindow import ConfigureWindow
    # import skimage.exposure
    #
    # import constants
    # import mainWindow_ui
    # from runSegmentation import runSegmentation
    #
    # class MainWindow(QMainWindow, mainWindow_ui.Ui_MainWindow):
    #     def __init__(self, parent=None):
    #         super(MainWindow, self).__init__(parent)
    #         self.setupUi(self)
    #
    #         self.sourceModel = QStandardItemModel(self.sourceListView)
    #         self.sourceListView.setModel(self.sourceModel)
    #
    #     @pyqtSlot()
    #     def on_browseSourceButton_clicked(self):
    #         # Read settings file
    #         settings = QSettings()
    #
    #         # Get the default open path when starting the file dialog, default is the user's home directory
    #         defaultOpenPath = settings.value('defaultOpenPath', str(Path.home()))
    #
    #         w = QFileDialog(self)
    #         w.setFileMode(QFileDialog.DirectoryOnly)
    #         w.setWindowTitle('Select source folders of subjects')
    #         w.setDirectory(defaultOpenPath)
    #         # Must use custom dialog if I want multiple directories to be selected
    #         w.setOption(QFileDialog.DontUseNativeDialog, True)
    #
    #         # Custom command to allow for multiple directories to be selected
    #         for view in self.findChildren((QListView, QTreeView)):
    #             if isinstance(view.model(), QFileSystemModel):
    #                 view.setSelectionMode(QAbstractItemView.ExtendedSelection)
    #
    #         # Start the dialog box and wait for input, it returns false if cancel was pressed
    #         if not w.exec():
    #             return
    #
    #         # Get selected directories
    #         dirs = w.selectedFiles()
    #
    #         # If empty, then cancel was pressed, return
    #         if not dirs:
    #             return
    #
    #         # Since there were items selected, set the default open path to be the directory the user was last in
    #         # Save it to settings
    #         defaultOpenPath = w.directory().absolutePath()
    #         settings.setValue('defaultOpenPath', defaultOpenPath)
    #
    #         # Check to make sure the directories are valid
    #         # Note: Don't use dir as variable name because it shadows built-in variable
    #         error = False
    #         for dir_ in dirs:
    #             if os.path.isdir(dir_):
    #                 self.sourceModel.appendRow(QStandardItem(dir_))
    #             else:
    #                 error = True
    #
    #         # If an error occurred, tell the user that the directory was not added
    #         if error:
    #             QMessageBox.critical(self, "Invalid directory",
    #                                  "One of the directories you chose was invalid. It was not added to the list")
    #
    #     @pyqtSlot()
    #     def on_runButton_clicked(self):
    #
    #
    #     @pyqtSlot()
    #     def on_configureButton_clicked(self):
    #         selectedIndices = self.sourceListView.selectedIndexes()
    #
    #         if self.sourceModel.rowCount() is 0:
    #             QMessageBox.warning(self, "No source directories",
    #                                 "There are no source directories in the list currently. Please add some folders "
    #                                 "before converting.")
    #             return
    #         elif len(selectedIndices) == 0:
    #             QMessageBox.warning(self, "No selected source directories",
    #                                 "There are no source directories selected currently. Please select one.")
    #             return
    #         elif len(selectedIndices) != 1:
    #             QMessageBox.warning(self, "Multiple selected directories",
    #                                 "There are currently more than one directories selected to configure. "
    #                                 "Please select only one.")
    #             return
    #
    #         # Get selected index text
    #         dataPath = selectedIndices[0].data()
    #
    #         # Load data from path
    #         fatImage, waterImage, config = self.loadFile(dataPath)
    #         if fatImage is None:
    #             return
    #
    #         self.configureWindow = ConfigureWindow(fatImage, waterImage, config, dataPath, parent=self)
    #         self.configureWindow.show()
    #
    #     def loadFile(self, dataPath):
    #         # Get the filenames for the rectified NIFTI files for current dataPath
    #         niiFatUpperFilename = os.path.join(dataPath, 'fatUpper.nii')
    #         niiFatLowerFilename = os.path.join(dataPath, 'fatLower.nii')
    #         niiWaterUpperFilename = os.path.join(dataPath, 'waterUpper.nii')
    #         niiWaterLowerFilename = os.path.join(dataPath, 'waterLower.nii')
    #         configFilename = os.path.join(dataPath, 'config.xml')
    #
    #         if not (os.path.isfile(niiFatUpperFilename) and os.path.isfile(niiFatLowerFilename) and os.path.isfile(
    #                 niiWaterUpperFilename) and os.path.isfile(niiWaterLowerFilename) and os.path.isfile(
    #             configFilename)):
    #             print('Missing required files from source path folder. Continuing...')
    #             return None, None, None
    #
    #         # Load unrectified NIFTI files for the current dataPath
    #         niiFatUpper = nib.load(niiFatUpperFilename)
    #         niiFatLower = nib.load(niiFatLowerFilename)
    #         niiWaterUpper = nib.load(niiWaterUpperFilename)
    #         niiWaterLower = nib.load(niiWaterLowerFilename)
    #
    #         # Load config XML file
    #         config = etree.parse(configFilename)
    #
    #         # Get the root of the config XML file
    #         configRoot = config.getroot()
    #
    #         # Piece together upper and lower images for fat and water
    #         # Retrieve the inferior and superior axial slice from config file for upper and lower images
    #         imageUpperTag = configRoot.find('imageUpper')
    #         imageLowerTag = configRoot.find('imageLower')
    #         imageUpperInferiorSlice = int(imageUpperTag.attrib['inferiorSlice'])
    #         imageUpperSuperiorSlice = int(imageUpperTag.attrib['superiorSlice'])
    #         imageLowerInferiorSlice = int(imageLowerTag.attrib['inferiorSlice'])
    #         imageLowerSuperiorSlice = int(imageLowerTag.attrib['superiorSlice'])
    #
    #         # Use inferior and superior axial slice to obtain the valid portion of the upper and lower fat and water images
    #         fatUpperImage = niiFatUpper.get_data()[:, :, imageUpperInferiorSlice:imageUpperSuperiorSlice]
    #         fatLowerImage = niiFatLower.get_data()[:, :, imageLowerInferiorSlice:imageLowerSuperiorSlice]
    #         waterUpperImage = niiWaterUpper.get_data()[:, :, imageUpperInferiorSlice:imageUpperSuperiorSlice]
    #         waterLowerImage = niiWaterLower.get_data()[:, :, imageLowerInferiorSlice:imageLowerSuperiorSlice]
    #
    #         # Concatenate the lower and upper image into one along the Z dimension
    #         fatImage = np.concatenate((fatLowerImage, fatUpperImage), axis=2)
    #         waterImage = np.concatenate((waterLowerImage, waterUpperImage), axis=2)
    #
    #         # Normalize the fat/water images so that the intensities are between (0.0, 1.0)
    #         # Also converts to float data type
    #         fatImage = skimage.exposure.rescale_intensity(fatImage.astype(float), out_range=(0.0, 1.0))
    #         waterImage = skimage.exposure.rescale_intensity(waterImage.astype(float), out_range=(0.0, 1.0))
    #
    #         # Set constant pathDir to be the current data path to allow writing/reading from the current directory
    #         constants.pathDir = dataPath
    #
    #         constants.nrrdHeaderDict = {'space': 'right-anterior-superior'}
    #         constants.nrrdHeaderDict['space directions'] = (niiFatUpper.header['srow_x'][0:-1],
    #                                                         niiFatUpper.header['srow_y'][0:-1],
    #                                                         niiFatUpper.header['srow_z'][0:-1])
    #
    #         constants.nrrdHeaderDict['space origin'] = (niiFatUpper.header['srow_x'][-1],
    #                                                     niiFatUpper.header['srow_y'][-1],
    #                                                     niiFatUpper.header['srow_z'][-1])
    #
    #         return fatImage, waterImage, config
