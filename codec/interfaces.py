from abc import ABCMeta, abstractmethod
from typing import List, Iterable, Union, Generic, TypeVar, Callable

import numpy as np
from numpy import ndarray

from threading import Lock

from codec.essential import BlockWeight


class InvalidArguments(Exception):

    def __init__(self, msg, cls):
        self.Msg = msg
        self.Cls = cls

    def __repr__(self):
        return "Invalid argument, {}, in class {}.".format(self.Msg, self.Cls)


T = TypeVar('T')


class netEncapsulation(Generic[T]):
    """
        Net Encapsulation, for network transmission.
    """

    def __init__(self, send_to_who: Union[Iterable[int], int], content: T):

        if isinstance(send_to_who, list):
            self.__target = send_to_who
        elif isinstance(send_to_who, int):
            self.__target = [send_to_who]
        elif isinstance(send_to_who, set):
            self.__target = list(send_to_who)
        else:
            raise InvalidArguments("Send to an unidentified node: {}".format(send_to_who), netEncapsulation)
        if isinstance(content, object):
            self.__packages = content
        else:
            raise InvalidArguments("Package is not required type.", netEncapsulation)
        self.__has_handled = False
        self.__has_sent = False

    @property
    def has_handled(self):
        return self.__has_handled

    @property
    def has_sent(self):
        return self.__has_sent

    def __setstate__(self, state: T):
        self.__target = None
        self.__has_handled = False
        self.__has_sent = False
        self.__packages = state

    def __getstate__(self) -> T:
        self.__has_sent = True
        return self.__packages

    def target(self) -> List[int]:
        return self.__target

    @property
    def content(self) -> T:
        self.__has_handled = True
        return self.__packages

    @content.setter
    def content(self, value: T):
        self.__packages = value


class Codec(metaclass=ABCMeta):

    def __init__(self, node_id: int):
        """
            Initialize a communication controller.
        :param node_id: id of current worker.
        """
        self.__node_id = node_id
        self.__updated_weight_buffer: [ndarray] = None
        self.__rw_lock = Lock()

    @property
    def node_id(self):
        return self.__node_id

    @abstractmethod
    def dispose(self):
        """
            Dispose this object and release all the memory.
        :return: None
        """
        pass

    @abstractmethod
    def update_blocks(self, block_weight: BlockWeight) -> Union[Iterable[netEncapsulation[T]], netEncapsulation[T], None]:
        """
            Update the weights generated by a specified block of sample to the cluster,
            function will return a tuple, the first element is the list of node IDs
            of the targets to be sent, the second element is the actual content json to
            be sent.
            Function return None if nothing to be sent.
            When the update process was done, it will check if there were
            enough intermediate values to rebuild full weights.
            such checking will be useless within Synchronized-Stochastic Gradient Descent algorithm.
        :param block_weight: weights generated by a specified block of sample
        :return: None if nothing to sent or NetEncapsulation like : (send target, json object).
        """
        pass

    @abstractmethod
    def receive_blocks(self, content: T) -> Union[Iterable[netEncapsulation[T]], netEncapsulation[T], None]:
        """
            Receive a json like dictionary from cluster.
            decompose the object and check if there were enough intermediate values to
            rebuild full weights.
            Available weights will be saved in self.updated_weight_buffer
        :param content: object, anything send by update_blocks will be received here.
        :return: Generator: for iterating packages to be sent with NetEncapsulation type
                None if nothing need to be sent.
        """
        pass

    def do_something_to_save_yourself(self) -> Union[Iterable[netEncapsulation[T]], netEncapsulation[T], None]:
        """
            If SSGD throws a timeout exception, this method will be called.
            This method were implemented intend to break the deadlock among nodes.
        :return: Generator: for iterating packages to be sent with NetEncapsulation type.
        """
        pass

    def record(self, message: str):
        from codec import GlobalSettings
        GlobalSettings.global_logger().log_message("Codec: {}, Report: {}.".format(self.__class__.__name__, message))

    def is_done(self) -> bool:
        """
            Check if all the coding and decoding process is done.
        :return: True if done, False if not done.
        """
        return self.__updated_weight_buffer is not None

    def get_result(self) -> ndarray:
        """
            Clear current weights buffer and return.
        :return: weights buffer: ndarray
        """
        assert self.__updated_weight_buffer is not None, 'No weights buffer available.'

        with self.__rw_lock:
            tmp = self.__updated_weight_buffer
            self.__updated_weight_buffer = None

        return tmp

    def set_result(self, content: ndarray, operation: Callable[[ndarray, ndarray], ndarray] = None):
        """
            Do some operations on current data.
        :param content: content used to modify
        :param operation: modify operation. Callable object, obtain the old result and content,
                          and returns a newer object.
                          def func(old_result: ndarray, new_content: ndarray) -> ndarray: # returns new result
        :return: None
        """
        if operation is None:
            def operation(x: ndarray, y: ndarray) -> ndarray: return x + y

        with self.__rw_lock:
            tmp = self.__updated_weight_buffer
            self.__updated_weight_buffer = operation(tmp if tmp is not None else np.asarray(0.0), content)
