# This Python file uses the following encoding: utf-8
import os
import sys
from PIL import Image
from multiprocessing import Value, Lock
from PySide6.QtWidgets import QApplication, QWidget, QFileDialog, QMessageBox, QProgressBar
from PySide6.QtCore import QThreadPool, QRunnable, QThread, QObject, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices
from ui_form import Ui_ImagePatcherUI
import logging

# Configure logging
logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)

class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        self.fn(*self.args, **self.kwargs)

class ImageProcessor(QObject):
    progressSignal = Signal(int)
    started = Signal()
    finished = Signal()

    def __init__(self, total_images=0):  # Default value for total_images
        super().__init__()
        self.total_images = total_images
        self.processed_images_counter = Value('i', 0)
        self.processed_images_counter_lock = Lock()
        self.progress_value = Value('i', 0)

    def setParameters(self, source_path, dest_path, dest_path_low_res, patch_size, resize_scale):
        self.source_path = source_path
        self.dest_path = dest_path
        self.dest_path_low_res = dest_path_low_res
        self.patch_size = patch_size
        self.resize_scale = resize_scale

    def setTotalImages(self, total_images):
        self.total_images = total_images

    @Slot()
    def process_images(self):
        self.started.emit()
        images_to_process = self.get_images_to_process(self.source_path)

        self.threadpool = QThreadPool()

        for image in images_to_process:
            worker = Worker(self.process_image,
                            image, self.dest_path, self.dest_path_low_res, self.patch_size, self.resize_scale,
                            self.processed_images_counter, self.processed_images_counter_lock, self.progress_value,
                            self.total_images)  # Add total_images here
            self.threadpool.start(worker)

        while not self.threadpool.waitForDone(100):  # wait 100ms, then continue
            self.progressSignal.emit(self.progress_value.value)

        # Once the pool finishes, we emit the final signal and the finished signal.
        self.finished.emit()

    def get_images_to_process(self, path):
        supported_formats = ['png', 'jpg', 'jpeg', 'tga']
        images = [os.path.join(path, f) for f in os.listdir(path) if f.split('.')[-1].lower() in supported_formats]
        return images

    @staticmethod
    def process_image(file, dest_path, dest_path_low_res, patch_size, resize_scale, processed_images_counter, counter_lock, progress_value, total_images):  # Add total_images here
        try:
            image = Image.open(file)
            width, height = image.size

            if width < patch_size or height < patch_size:
                logging.info(f"Skipping {file} - dimensions are less than {patch_size}.")
                return

            logging.info(f"Processing {file}...")
            num_patches_width = width // patch_size
            num_patches_height = height // patch_size

            for i in range(num_patches_width):
                for j in range(num_patches_height):
                    x_pos = i * patch_size
                    y_pos = j * patch_size

                    if x_pos < width and y_pos < height:
                        box = (x_pos, y_pos, min(x_pos + patch_size, width), min(y_pos + patch_size, height))
                        cropped = image.crop(box)

                        output_file = os.path.join(dest_path,
                                                f"{os.path.splitext(os.path.basename(file))[0]}_{i}_{j}.png")
                        cropped.save(output_file)

                        try:
                            # Resize for low-resolution
                            new_size = patch_size // resize_scale
                            if new_size <= 0:
                                logging.warning(f"new_size is {new_size}, check resize_scale value.")
                            low_res = cropped.resize((new_size, new_size), Image.LANCZOS)
                            low_res.save(os.path.join(dest_path_low_res, f"{os.path.splitext(os.path.basename(file))[0]}_{i}_{j}.png"))
                        except Exception as e:
                            logging.error(f"Failed to process low-res image for file {file} with error {e}")

                    with counter_lock:  # Lock the counter while updating it
                        processed_images_counter.value += 1
                        progress_value.value = int((processed_images_counter.value / float(total_images)) * 100)

        except Exception as e:
            logging.error(f"Failed to process image {file} with error {e}")

class ImagePatcherUI(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_ImagePatcherUI()
        self.ui.setupUi(self)

        self.ui.logoButton.clicked.connect(self.open_url)
        self.ui.browseSourceButton.clicked.connect(self.browseForSource)
        self.ui.browseOutputButton.clicked.connect(self.browseForOutput)
        self.ui.browseLowResOutputButton.clicked.connect(self.browseForLowResOutput)
        self.ui.processButton.clicked.connect(self.startProcessing)
        self.progressBar = self.findChild(QProgressBar, 'progressBar')

        self.ui.progressBar.hide()
        self.ui.progressLabel.setText("Welcome to the Image Patcher UI! Please choose source & output folders to get started :)")

        self.imageProcessor = ImageProcessor()
        self.imageProcessor.progressSignal.connect(self.updateProgressBar)
        self.imageProcessorThread = QThread()
        self.imageProcessor.moveToThread(self.imageProcessorThread)
        self.imageProcessorThread.started.connect(self.imageProcessor.process_images)
        self.imageProcessor.finished.connect(self.imageProcessorThread.quit)
        self.imageProcessor.finished.connect(self.onProcessFinished)

    def open_url(self):
        QDesktopServices.openUrl(QUrl("https://jmd.vc"))

    def updateProgressBar(self, value):
        self.progressBar.setValue(value)

    def browseForSource(self):
        directory = QFileDialog.getExistingDirectory(self, 'Select Source Folder')
        if directory:
            self.ui.sourceLineEdit.setText(directory)

    def browseForOutput(self):
        directory = QFileDialog.getExistingDirectory(self, 'Select Output Folder')
        if directory:
            self.ui.outputLineEdit.setText(directory)

    def browseForLowResOutput(self):
        directory = QFileDialog.getExistingDirectory(self, 'Select Low-Res Output Folder')
        if directory:
            self.ui.lowResOutputLineEdit.setText(directory)

    def startProcessing(self):
        try:
            source_path = self.ui.sourceLineEdit.text()
            dest_path = self.ui.outputLineEdit.text()
            dest_path_low_res = self.ui.lowResOutputLineEdit.text()
            patch_size = int(self.ui.patchSizeText.toPlainText())
            scale_text = self.ui.comboBoxScale.currentText()
            resize_scale = int(scale_text.strip("x"))
        except ValueError:
            QMessageBox.critical(self, "Invalid input", "Patch size and scale must be valid integers")
            return

        self.ui.processButton.setDisabled(True)

        self.ui.progressLabel.hide()
        self.ui.progressBar.show()

        num_images = len(list(self.imageProcessor.get_images_to_process(source_path)))
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(100)
        self.progressBar.setValue(0)

        self.imageProcessor.setTotalImages(num_images)
        self.imageProcessor.setParameters(source_path, dest_path, dest_path_low_res, patch_size, resize_scale)

        self.imageProcessorThread.start()

    @Slot()
    def onProcessFinished(self):
        self.ui.processButton.setDisabled(False)
        self.ui.progressBar.hide()
        self.ui.progressLabel.setText("The images were successfully processed! Click 'Process' to run again.")
        self.ui.progressLabel.show()
        QMessageBox.information(self, "Processing complete", "The images were successfully processed!")

def main():
    app = QApplication(sys.argv)

    window = ImagePatcherUI()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
