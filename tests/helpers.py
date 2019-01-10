import os
import sys
import unittest
import tempfile
from contextlib import contextmanager

import six
import numpy as np
import pandas as pd
from sklearn import datasets
from sklearn.model_selection import StratifiedShuffleSplit
from matplotlib import pyplot as plt
from matplotlib.testing.compare import compare_images

from neupy import algorithms, layers, utils, init
from neupy.storage import save_dict, load_dict


def simple_classification(n_samples=100, n_features=10, random_state=33):
    """
    Generate simple classification task for training.

    Parameters
    ----------
    n_samples : int
        Number of samples in dataset.
    n_features : int
        Number of features for each sample.
    random_state : int
        Random state to make results reproducible.

    Returns
    -------
    tuple
        Returns tuple that contains 4 variables. There are input train,
        input test, target train, target test respectevly.
    """
    X, y = datasets.make_classification(
        n_samples=n_samples,
        n_features=n_features,
        random_state=random_state,
    )
    shuffle_split = StratifiedShuffleSplit(
        n_splits=1,
        train_size=0.6,
        test_size=0.1,
        random_state=random_state,
    )

    train_index, test_index = next(shuffle_split.split(X, y))
    x_train, x_test = X[train_index], X[test_index]
    y_train, y_test = y[train_index], y[test_index]

    return x_train, x_test, y_train, y_test


@contextmanager
def catch_stdout():
    """
    Context manager that catches output in terminal and returns
    StringIO instance.

    Yields
    ------
    StringIO instance

    Examples
    --------
    >>> with catch_stdout() as out:
    ...     print("Unittest")
    ...     terminal_output = out.getvalue()
    ...     self.assertIn("test", terminal_output)
    """
    old_out = sys.stdout
    old_err = sys.stderr

    out = six.StringIO()

    sys.stdout = out
    sys.stderr = out

    yield out

    sys.stdout = old_out
    sys.stderr = old_err


def compare_networks(default_class, tested_class, data, **kwargs):
    """
    Compare two network arcitectures.

    Parameters
    ----------
    default_class : BaseNetwork instance
    tested_class : BaseNetwork instance
    data : tuple
    **kwargs :

    Raises
    ------
    AssertionError
        Raise exception when first network have better prediction
        accuracy then the second one.
    """
    epochs = kwargs.pop('epochs', 100)
    show_comparison_plot = kwargs.pop('show_comparison_plot', False)

    # Compute result for default network (which must be slower)
    network = default_class(**kwargs)

    if hasattr(network, 'connection'):
        initial_parameters = save_dict(network.network)

    network.train(*data, epochs=epochs)

    network_default_error = network.training_errors[-1]
    errors1 = network.training_errors

    # Compute result for test network (which must be faster)
    if hasattr(network, 'connection'):
        load_dict(network.network, initial_parameters)

    network = tested_class(**kwargs)

    network.train(*data, epochs=epochs)
    network_tested_error = network.training_errors[-1]
    errors2 = network.training_errors

    if show_comparison_plot:
        error_range = np.arange(max(len(errors1), len(errors2)))
        plt.plot(error_range[:len(errors1)], errors1)
        plt.plot(error_range[:len(errors2)], errors2)
        plt.show()

    if network_default_error <= network_tested_error:
        raise AssertionError("First network has smaller error ({}) that the "
                             "second one ({}).".format(network_default_error,
                                                       network_tested_error))


def format_image_name(name):
    """
    Add to image name prefix that identify Python versions.
    """
    name_prefix = 'test_py3_' if six.PY3 else 'test_py2_'
    return name_prefix + name


@contextmanager
def image_comparison(original_image_path, figsize=(10, 10), tol=1e-3):
    """
    Context manager that initialize figure that should contain figure
    that should be compared with expected one.

    Parameters
    ----------
    original_image_path : str
        Path to original image that will use for comparison.

    figsize : tuple
        Figure size. Defaults to ``(10, 10)``.

    tol : float
        Comparison tolerance. Defaults to ``1e-3``.

    Raises
    ------
    AssertionError
        Exception would be trigger in case when generated images and
        original one are different.
    """
    currentdir = os.path.abspath(os.path.dirname(__file__))
    original_image_path = os.path.join(currentdir, original_image_path)

    with tempfile.NamedTemporaryFile(suffix='.png') as f:
        figure = plt.figure(figsize=figsize)

        yield figure

        figure.savefig(f.name)
        error = compare_images(f.name, original_image_path, tol=tol)

        if error:
            raise AssertionError("Image comparison failed. \n"
                                 "Information: {}".format(error))


def reproducible_network_train(seed=0, epochs=500, **additional_params):
    """
    Make a reproducible train for Gradient Descent based neural
    network with a XOR problem and return trained network.

    Parameters
    ----------
    seed : int
        Random State seed number for reproducibility. Defaults to ``0``.
    epochs : int
        Number of epochs for training. Defaults to ``500``.
    **additional_params
        Aditional parameters for Neural Network.

    Returns
    -------
    GradientDescent instance
        Returns trained network.
    """
    utils.reproducible(seed)

    xor_x_train = np.array([[-1, -1], [-1, 1], [1, -1], [1, 1]])
    xor_y_train = np.array([[1, -1, -1, 1]]).T

    xavier_normal = init.XavierNormal()
    tanh_weight1 = xavier_normal.sample((2, 5), return_array=True)
    tanh_weight2 = xavier_normal.sample((5, 1), return_array=True)

    network = algorithms.GradientDescent(
        network=[
            layers.Input(2),
            layers.Tanh(5, weight=tanh_weight1),
            layers.Tanh(1, weight=tanh_weight2),
        ],
        batch_size=None,
        **additional_params
    )
    network.train(xor_x_train, xor_y_train, epochs=epochs)
    return network


def vectors_for_testing(vector, is_feature1d=True):
    """
    Function generate different possible variations of one vector.
    That feature useful for testing algorithms input data.

    Parameters
    ----------
    vector : ndarray
        Vector that would be transformed in different data types.
    is_feature1d : bool
        Parameter explain the vector type. Parameter equal to ``True`` mean
        that input data a banch of samples that contains one feature each.
        Defaults to ``True``.

    Raises
    ------
    ValueError
        If input is not a vector

    Returns
    -------
    list
        List that contains the same vectors in different data types like
        numpy 2D vector or pandas Data Frame
    """

    if vector.ndim != 1 and min(vector.shape) != 1:
        raise ValueError("Input should be a vector")

    shape2d = (vector.size, 1) if is_feature1d else (1, vector.size)

    vectors_list = []
    if vector.ndim == 1:
        vectors_list.extend([vector, pd.Series(vector)])

    vectors_list.extend([
        vector.reshape(shape2d),
        pd.DataFrame(vector.reshape(shape2d))])

    return vectors_list


def skip_image_comparison_if_specified(func):
    """
    Decorator identifies tests that involve image comparison.
    Before run test function check if environemnt variable
    `SKIP_PLOT_TEST` exists and has non-empty value. If it exists,
    step will be skipped.

    Parameters
    ----------
    func : function
        Any function that you need to override.

    Returns
    -------
    function
        Overrided function.
    """
    decorator = unittest.skipIf(
        os.environ.get('SKIP_PLOT_TEST', None),
        "skip tests that involve image comparison"
    )
    return decorator(func)
