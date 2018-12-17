import numpy as np
from sklearn.preprocessing import OneHotEncoder
from sklearn.model_selection import train_test_split
from sklearn import metrics, datasets

from neupy.layers import *
from neupy import algorithms


def load_data():
    mnist = datasets.fetch_mldata('MNIST original')
    data = mnist.data.reshape(-1, 28, 28, 1)

    target_scaler = OneHotEncoder(
        sparse=False,
        categories='auto',
        dtype=np.float32,
    )
    target = mnist.target.reshape(-1, 1)
    target = target_scaler.fit_transform(target)

    x_train, x_test, y_train, y_test = train_test_split(
        data.astype(np.float32), target,
        test_size=(1 / 7.)
    )

    mean = x_train.mean(axis=(0, 1, 2))
    std = x_train.std(axis=(0, 1, 2))

    x_train -= mean
    x_train /= std
    x_test -= mean
    x_test /= std

    return x_train, x_test, y_train, y_test


network = algorithms.Momentum(
    [
        Input((28, 28, 1)),

        Convolution((3, 3, 32)) > BatchNorm() > Relu(),
        Convolution((3, 3, 48)) > BatchNorm() > Relu(),
        MaxPooling((2, 2)),

        Convolution((3, 3, 64)) > BatchNorm() > Relu(),
        MaxPooling((2, 2)),

        Reshape(),
        Linear(1024) > BatchNorm() > Relu(),
        Softmax(10),
    ],

    # Using categorical cross-entropy as a loss function.
    # It's suitable for classification with 3 and more classes.
    error='categorical_crossentropy',

    # Mini-batch size
    batch_size=128,

    # Step == Learning rate
    # Step decay algorithm minimizes learning step
    # monotonically after each iteration.
    step=algorithms.step_decay(
        initial_value=0.05,
        # Parameter controls step redution frequency. The higher
        # the value the slower step parameter decreases.
        reduction_freq=500,
    ),

    # Shows information about algorithm and
    # training progress in terminal
    verbose=True,

    # Randomly shuffles training dataset before every epoch
    shuffle_data=True,
)

# Shows networks architecture in terminal's output
network.architecture()

x_train, x_test, y_train, y_test = load_data()

# Train for 4 epochs
network.train(x_train, y_train, x_test, y_test, epochs=4)

# Make prediction on the test dataset
y_predicted = network.predict(x_test).argmax(axis=1)
y_test_labels = np.asarray(y_test.argmax(axis=1)).reshape(len(y_test))

# Compare network's predictions to the actual label values
# and build simple classification report.
print(metrics.classification_report(y_test_labels, y_predicted))
score = metrics.accuracy_score(y_test_labels, y_predicted)
print("Validation accuracy: {:.2%}".format(score))
