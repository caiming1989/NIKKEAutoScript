import os

import imageio

from module.base.button import Button
from functools import cached_property
from module.base.resource import Resource
from module.base.utils import *
from module.map_detection.utils import Points


class Template(Resource):
    def __init__(self, file):
        """
        Args:
            file (dict[str], str): Filepath of template file.
        """
        self.raw_file = file
        self._image = None
        self._image_binary = None

        self.resource_add(self.file)

    cached = ['file', 'name', 'is_gif']

    @cached_property
    def file(self):
        return self.parse_property(self.raw_file)

    @cached_property
    def name(self):
        return os.path.splitext(os.path.basename(self.file))[0].upper()

    @cached_property
    def is_gif(self):
        return os.path.splitext(self.file)[1] == '.gif'

    @property
    def image(self):
        if self._image is None:
            if self.is_gif:
                self._image = []
                channel = 0
                for image in imageio.mimread(self.file):
                    if not channel:
                        channel = len(image.shape)
                    if channel == 3:
                        image = image[:, :, :3].copy()
                    elif len(image.shape) == 3:
                        # Follow the first frame
                        image = image[:, :, 0].copy()

                    image = self.pre_process(image)
                    self._image += [image, cv2.flip(image, 1)]
            else:
                self._image = self.pre_process(load_image(self.file))

        return self._image

    @property
    def image_binary(self):
        if self._image_binary is None:
            if self.is_gif:
                self._image_binary = []
                for image in self.image:
                    image_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                    _, image_binary = cv2.threshold(image_gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
                    self._image_binary.append(image_binary)
            else:
                image_gray = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)
                _, self._image_binary = cv2.threshold(image_gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

        return self._image_binary

    @image.setter
    def image(self, value):
        self._image = value

    def resource_release(self):
        super().resource_release()
        self._image = None
        self._image_binary = None

    def pre_process(self, image):
        """
        Args:
            image (np.ndarray):

        Returns:
            np.ndarray:
        """
        return image

    @cached_property
    def size(self):
        if self.is_gif:
            return self.image[0].shape[0:2][::-1]
        else:
            return self.image.shape[0:2][::-1]

    def match(self, image, scaling=1.0, similarity=0.85):
        """
        Args:
            image:
            scaling (int, float): Scale the template to match image
            similarity (float): 0 to 1.

        Returns:
            bool: If matches.
        """
        scaling = 1 / scaling
        if scaling != 1.0:
            image = cv2.resize(image, None, fx=scaling, fy=scaling)

        if self.is_gif:
            for template in self.image:
                res = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
                _, sim, _, _ = cv2.minMaxLoc(res)
                # print(self.file, sim)
                if sim > similarity:
                    return True

            return False

        else:
            res = cv2.matchTemplate(image, self.image, cv2.TM_CCOEFF_NORMED)
            _, sim, _, _ = cv2.minMaxLoc(res)
            # print(self.file, sim)
            return sim > similarity

    def match_binary(self, image, similarity=0.85):
        """
        Use template match after binarization.

        Args:
            image:
            similarity (float): 0 to 1.

        Returns:
            bool: If matches.
        """
        if self.is_gif:
            # graying
            image_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            # binarization
            _, image_binary = cv2.threshold(image_gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
            for template in self.image_binary:
                # template matching
                res = cv2.matchTemplate(template, image_binary, cv2.TM_CCOEFF_NORMED)
                _, sim, _, _ = cv2.minMaxLoc(res)
                # print(self.file, sim)
                if sim > similarity:
                    return True

            return False

        else:
            # graying
            image_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            # binarization
            _, image_binary = cv2.threshold(image_gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
            # template matching
            res = cv2.matchTemplate(self.image_binary, image_binary, cv2.TM_CCOEFF_NORMED)
            _, sim, _, _ = cv2.minMaxLoc(res)
            # print(self.file, sim)
            return sim > similarity

    def _point_to_button(self, point, image=None, name=None):
        """
        Args:
            point:
            image (np.ndarray): Screenshot. If provided, load color and image from it.
            name (str):

        Returns:
            Button:
        """
        if name is None:
            name = self.name
        area = area_offset(area=(0, 0, *self.size), offset=point)
        button = Button(area=area, color=(), button=area, name=name)
        if image is not None:
            button.load_color(image)
        return button

    def match_result(self, image, name=None):
        """
        Args:
            image:
            name (str):

        Returns:
            float: Similarity
            Button:
        """
        res = cv2.matchTemplate(image, self.image, cv2.TM_CCOEFF_NORMED)
        _, sim, _, point = cv2.minMaxLoc(res)
        # print(self.file, sim)

        button = self._point_to_button(point, image=image, name=name)
        return sim, button

    def match_result_with_scale(self, image, scale_range=(0.7, 1.3), scale_step=0.05, name=None):
        """
        Multi-scale template matching that finds the best match across a range of scales.

        Args:
            image: Screenshot image
            scale_range (tuple[float, float]): (min_scale, max_scale)
            scale_step (float): Scale increment
            name (str): Button name

        Returns:
            float: Best similarity
            Button: Best matched button with location
        """
        best_sim = -1
        best_point = None
        best_scale = 1.0

        scale = scale_range[0]
        while scale <= scale_range[1]:
            resized = cv2.resize(self.image, (0, 0), fx=scale, fy=scale)
            if resized.shape[0] > image.shape[0] or resized.shape[1] > image.shape[1]:
                scale += scale_step
                continue

            res = cv2.matchTemplate(image, resized, cv2.TM_CCOEFF_NORMED)
            _, sim, _, point = cv2.minMaxLoc(res)

            if sim > best_sim:
                best_sim = sim
                best_point = point
                best_scale = scale

            scale += scale_step

        if best_point is None:
            button = self._point_to_button((0, 0), image=image, name=name)
            return -1, button

        w, h = int(self.size[0] * best_scale), int(self.size[1] * best_scale)
        area = (best_point[0], best_point[1], best_point[0] + w, best_point[1] + h)
        button = Button(area=area, color=(), button=area, name=name or self.name)
        if image is not None:
            button.load_color(image)
        return best_sim, button

    def match_multi(self, image, scaling=1.0, similarity=0.85, threshold=3, name=None):
        """
        Args:
            image:
            scaling (int, float): Scale the template to match image
            similarity (float): 0 to 1.
            threshold (int): Distance to delete nearby results.
            name (str):

        Returns:
            list[Button]:
        """
        scaling = 1 / scaling
        if scaling != 1.0:
            image = cv2.resize(image, None, fx=scaling, fy=scaling)

        raw = image
        if self.is_gif:
            result = []
            for template in self.image:
                res = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
                res = np.array(np.where(res > similarity)).T[:, ::-1].tolist()
                result += res
            result = np.array(result)
        else:
            result = cv2.matchTemplate(image, self.image, cv2.TM_CCOEFF_NORMED)
            result = np.array(np.where(result > similarity)).T[:, ::-1]

        # result: np.array([[x0, y0], [x1, y1], ...)
        if scaling != 1.0:
            result = np.round(result / scaling).astype(int)
        result = Points(result).group(threshold=threshold)
        return [self._point_to_button(point, image=raw, name=name) for point in result]
