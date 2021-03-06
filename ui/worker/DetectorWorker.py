from datetime import timedelta
from datetime import datetime
from threading import Thread
from PyQt5.QtCore import QThread, pyqtSignal

from detector.object_detection.ObjectDetection import ObjectDetection
from detector.event.assault.main import AssaultEvent
from detector.event.falldown.main import FalldownEvent
from detector.event.wanderer.main import WandererEvent
from detector.event.obstacle.main import ObstacleEvent
from detector.event.kidnapping.main import KidnappingEvent
from detector.event.tailing.main import TailingEvent
from detector.event.reid.main import ReidEvent


class DetectorWorker(QThread):
    table_widget_add_row_signal = pyqtSignal(int, int, int, str)
    edit_text_log_signal = pyqtSignal(str)

    def __init__(self, video_worker, send_message_worker, parent=None):
        super().__init__()
        self.video_worker = video_worker
        self.send_message_worker = send_message_worker
        self.run_detection = False


    def __del__(self):
        del self

    def print_video_log(self):
        self.edit_text_log_signal.emit(self.video_worker.get_video_worker_info())

    def initialize_models(self):
        success_event_models = ""
        fail_event_models = ""

        # Load object detection model
        try :
            import pycuda.autoinit
            from detector.object_detection.yolov4 import YOLOv4

            self.edit_text_log_signal.emit("VERBOSE:\tLoading object detection model....")
            import time
            start = time.time()
            self.model_object_detection = YOLOv4()
            end = time.time()
            self.edit_text_log_signal.emit("VERBOSE:\tSucceeded to load object detection model - ({})\n\tmodel name: {} ".format(timedelta(seconds=end-start), self.model_object_detection.model_name))
        except:
            self.model_object_detection = ObjectDetection()
            self.edit_text_log_signal.emit("ERROR: Failed to load object detection model ")

        self.event_models = []

        # Load assault event detection model
        try :
            model_event_assault = AssaultEvent()
            self.event_models.append(model_event_assault)
            success_event_models += "{} ".format(model_event_assault.model_name)
        except :
            fail_event_models += "{} ".format("assault")

        # Load wanderer event detection model
        try :
            model_event_falldown = FalldownEvent()
            self.event_models.append(model_event_falldown)
            success_event_models += "{} ".format(model_event_falldown.model_name)
        except :
            fail_event_models += "{} ".format("wanderer")

        # Load wanderer event detection model
        try :
            model_event_wanderer = WandererEvent()
            self.event_models.append(model_event_wanderer)
            success_event_models += "{} ".format(model_event_wanderer.model_name)
        except :
            fail_event_models += "{} ".format("wanderer")

        # Load obstacle event detection model
        try :
            model_event_obstacle = ObstacleEvent()
            self.event_models.append(model_event_obstacle)
            success_event_models += "{} ".format(model_event_obstacle.model_name)
        except :
            fail_event_models += "{} ".format("obstacle")

        # Load tailing event detection model
        try :
            model_event_tailing = TailingEvent()
            self.event_models.append(model_event_tailing)
            success_event_models += "{} ".format(model_event_tailing.model_name)
        except :
            fail_event_models += "{} ".format("tailing")

        # Load kidnapping event detection model
        try :
            model_event_kidnapping = KidnappingEvent()
            self.event_models.append(model_event_kidnapping)
            success_event_models += "{} ".format(model_event_kidnapping.model_name)
        except :
            fail_event_models += "{} ".format("kidnapping")

        # Load reid event detection model
        try :
            model_event_reid = ReidEvent()
            self.event_models.append(model_event_reid)
            success_event_models += "{} ".format(model_event_reid.model_name)
        except :
            fail_event_models += "{} ".format("reid")

        if len(success_event_models) > 0 :
            self.edit_text_log_signal.emit("VERBOSE:\tSucceeded to load event models\n\t( {})".format(success_event_models))
        if len(fail_event_models) > 0:
            self.edit_text_log_signal.emit("ERROR: Failed to load event models( {})".format(fail_event_models))

        self.button_start.setEnabled(True)

    def add_row(self, index, row_number, frame_number, event_result):
        self.table_widget_add_row_signal.emit(index, row_number, 0, str(frame_number + 1))
        self.table_widget_add_row_signal.emit(index, row_number, 1, "{}".format(self.convert_frame_number_to_timestamp(frame_number)))
        self.table_widget_add_row_signal.emit(index, row_number, 2, str(event_result))

    def run(self):
        self.run_detection = True
        analysis_frame_count = 0

        self.print_video_log()
        self.initialize_models()

        is_ended = False
        while self.run_detection:
            if not self.video_worker.run_video:
                if is_ended == False :
                    self.edit_text_log_signal.emit("VERBOSE:\tAnalysis End - ({})".format(str(timedelta(seconds=self.video_worker.running_time))))
                    is_ended = True

            if len(self.video_worker.frame_queue) > 0:
                frame_info = self.video_worker.frame_queue.pop(0)

                object_detection_result = self.model_object_detection.inference_by_image(frame_info[1], confidence_threshold=0.3)

                result = dict()
                result["image"] = "{0:06d}.jpg".format(frame_info[0])
                result["module"] = self.model_object_detection.model_name
                result["cam_id"] = 0  # TODO
                result["frame_number"] = int(frame_info[0])
                result["results"] = []
                result["results"].append(object_detection_result)

                self.video_worker.object_detection_result_queue.append(object_detection_result)

                event_threads = []
                for event_model in self.event_models:
                    event_thread = Thread(target=event_model.inference, args=(result["results"],))
                    event_threads.append(event_thread)

                for event_thread in event_threads:
                    event_thread.start()

                for event_thread in event_threads:
                    event_thread.join()

                result["event_result"] = dict()
                for event_model in self.event_models:
                    result["event_result"][event_model.model_name] = event_model.result
                self.send_message_worker.result_queue.append(result)

                self.add_row(0, analysis_frame_count, frame_info[0], self.get_objects(result["results"][0]))
                for i, event_model in enumerate(self.event_models):
                    self.add_row(i + 1, analysis_frame_count, frame_info[0], event_model.result)

                analysis_frame_count += 1


    def get_objects(self, object_detection_results):
        result = ""
        for object_detection_result in object_detection_results:
            object = object_detection_result["label"][0]
            label = object["description"]
            score = object["score"]
            x = object_detection_result["position"]["x"]
            y = object_detection_result["position"]["y"]
            w = object_detection_result["position"]["w"]
            h = object_detection_result["position"]["h"]
            result += "{}:{:.2f}({},{},{},{}), ".format(label, score, x, y, w, h)

        return result

    def convert_frame_number_to_timestamp(self, frame_number):
        return timedelta(seconds=frame_number/self.video_worker.video_fps)

    def connect_button_start(self, button_start):
        self.button_start = button_start
