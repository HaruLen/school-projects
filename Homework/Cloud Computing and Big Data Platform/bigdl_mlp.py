#
# Copyright 2016 The BigDL Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from optparse import OptionParser
from bigdl.dataset import mnist
from bigdl.dataset.transformer import *
from bigdl.nn.layer import *
from bigdl.nn.criterion import *
from bigdl.optim.optimizer import *
from bigdl.util.common import *


def build_model(class_num):
    model = Sequential()
    model.add(Reshape([784, ]))
    model.add(Linear(784, 512))
    model.add(ReLU())
    model.add(Dropout(0.2))
    model.add(Linear(512, 512))
    model.add(ReLU())
    model.add(Dropout(0.2))
    model.add(Linear(512, class_num))
    model.add(LogSoftMax())
    return model


def get_mnist(sc, data_type="train", location="/tmp/mnist"):
    """
    Get and normalize the mnist data. We would download it automatically
    if the data doesn't present at the specific location.
    :param sc: SparkContext
    :param data_type: training data or testing data
    :param location: Location storing the mnist
    :return: A RDD of (features: Ndarray, label: Ndarray)
    """
    (images, labels) = mnist.read_data_sets(location, data_type)
    images = sc.parallelize(images)
    labels = sc.parallelize(labels + 1) # Target start from 1 in BigDL
    record = images.zip(labels)
    return record


if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("-a", "--action", dest="action", default="train")
    parser.add_option("-b", "--batchSize", type=int, dest="batchSize", default="128")
    parser.add_option("-o", "--modelPath", dest="modelPath", default="/tmp/lenet5/model.470")
    parser.add_option("-c", "--checkpointPath", dest="checkpointPath", default="/tmp/lenet5")
    parser.add_option("-t", "--endTriggerType", dest="endTriggerType", default="epoch")
    parser.add_option("-n", "--endTriggerNum", type=int, dest="endTriggerNum", default="5")
    parser.add_option("-d", "--dataPath", dest="dataPath", default="/tmp/mnist")

    (options, args) = parser.parse_args(sys.argv)

    sc = SparkContext(appName="lenet5", conf=create_spark_conf())
    redire_spark_logs()
    show_bigdl_info_logs()
    init_engine()

    if options.action == "train":
        def get_end_trigger():
            if options.endTriggerType.lower() == "epoch":
                return MaxEpoch(options.endTriggerNum)
            else:
                return MaxIteration(options.endTriggerNum)

        train_data = get_mnist(sc, "train", options.dataPath)\
            .map(lambda rec_tuple: (normalizer(rec_tuple[0], mnist.TRAIN_MEAN, mnist.TRAIN_STD),
                               rec_tuple[1]))\
            .map(lambda t: Sample.from_ndarray(t[0], t[1]))
        test_data = get_mnist(sc, "test", options.dataPath)\
            .map(lambda rec_tuple: (normalizer(rec_tuple[0], mnist.TEST_MEAN, mnist.TEST_STD),
                               rec_tuple[1]))\
            .map(lambda t: Sample.from_ndarray(t[0], t[1]))
        optimizer = Optimizer(
            model=build_model(10),
            training_rdd=train_data,
            criterion=ClassNLLCriterion(),
            optim_method=RMSprop(learningrate=0.001),
            end_trigger=get_end_trigger(),
            batch_size=options.batchSize)
        optimizer.set_validation(
            batch_size=options.batchSize,
            val_rdd=test_data,
            trigger=EveryEpoch(),
            val_method=[Top1Accuracy()]
        )
        optimizer.set_checkpoint(EveryEpoch(), options.checkpointPath)
        trained_model = optimizer.optimize()
        parameters = trained_model.parameters()
    elif options.action == "test":
        # Load a pre-trained model and then validate it through top1 accuracy.
        test_data = get_mnist(sc, "test").map(
            normalizer(mnist.TEST_MEAN, mnist.TEST_STD))
        model = Model.load(options.modelPath)
        results = model.evaluate(test_data, options.batchSize, [Top1Accuracy()])
        for result in results:
            print(result)
    sc.stop()