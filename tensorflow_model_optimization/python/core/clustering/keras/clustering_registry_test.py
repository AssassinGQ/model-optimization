# Copyright 2019 The TensorFlow Authors. All Rights Reserved.
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
# ==============================================================================
"""Tests for keras clustering registry API."""

from absl.testing import parameterized
import tensorflow as tf

from tensorflow_model_optimization.python.core.clustering.keras import clusterable_layer
from tensorflow_model_optimization.python.core.clustering.keras import clustering_registry
from tensorflow_model_optimization.python.core.clustering.keras.cluster_config import GradientAggregation

keras = tf.keras
k = keras.backend
layers = keras.layers

errors_impl = tf.errors
test = tf.test

ClusterRegistry = clustering_registry.ClusteringRegistry
ClusteringLookupRegistry = clustering_registry.ClusteringLookupRegistry


class ClusteringAlgorithmTest(tf.test.TestCase, parameterized.TestCase):
  """Unit tests for clustering lookup algorithms."""

  def _check_pull_values(self, clustering_algo, pulling_indices,
                         expected_output):
    pulling_indices = tf.convert_to_tensor(pulling_indices)

    clustered_weight = clustering_algo.get_clustered_weight(
        pulling_indices,
        original_weight=tf.zeros(pulling_indices.shape, dtype=tf.float32))
    self.assertAllEqual(clustered_weight, expected_output)

  def _check_gradients_clustered_weight(
      self,
      clustering_algo,
      weight,
      pulling_indices,
      expected_grad_centroids,
  ):
    pulling_indices = tf.convert_to_tensor(pulling_indices)
    cluster_centroids = clustering_algo.cluster_centroids

    with tf.GradientTape(persistent=True) as t:
      t.watch(weight)
      t.watch(cluster_centroids)

      out = clustering_algo.get_clustered_weight(
          pulling_indices, original_weight=weight)

    grad_original_weight = t.gradient(out, weight)
    grad_cluster_centroids = t.gradient(out, cluster_centroids)
    # Because of tf.gather, the grad will be of type tf.IndexedSlices
    # Convert it back to a tf.tensor
    grad_cluster_centroids = tf.convert_to_tensor(grad_cluster_centroids)

    # grad_original_weight with respect to out should always be 1s
    expected_grad_weight = tf.ones(shape=grad_original_weight.shape)

    self.assertAllEqual(grad_original_weight, expected_grad_weight)
    self.assertAllEqual(grad_cluster_centroids, expected_grad_centroids)

  @parameterized.parameters(
      (
          GradientAggregation.AVG,
          [[1, 1, 1, 1], [1, 0, 0, 0], [0, 1, 1, 0], [0, 0, 1, 0]],
          [1, 1],
      ),
      (
          GradientAggregation.SUM,
          [[1, 1, 1, 1], [1, 0, 0, 0], [0, 1, 1, 0], [0, 0, 1, 0]],
          [8, 8],
      ),
      (
          GradientAggregation.AVG,
          [[1, 1, 1, 1], [1, 1, 1, 0], [0, 1, 1, 0], [0, 0, 1, 0]],
          [1, 1],
      ),
      (
          GradientAggregation.AVG,
          [[1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1]],
          [0, 1],
      ),
      (
          GradientAggregation.SUM,
          [[1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1]],
          [0, 16],
      ),
  )
  def testDenseWeightsCAGrad(
      self,
      cluster_gradient_aggregation,
      pulling_indices,
      expected_grad_centroids,
  ):
    """Verifies that the gradients of DenseWeightsCA work as expected."""
    clustering_centroids = tf.Variable([-0.800450444, 0.864694357])
    weight = tf.constant(
        [[0.220442653, 0.854694366, 0.0328432359, 0.506857157],
         [0.0527950861, -0.659555554, -0.849919915, -0.54047],
         [-0.305815876, 0.0865516588, 0.659202456, -0.355699599],
         [-0.348868281, -0.662001, 0.6171574, -0.296582848]])

    clustering_algo = clustering_registry.DenseWeightsCA(
        clustering_centroids, cluster_gradient_aggregation)
    self._check_gradients_clustered_weight(
        clustering_algo,
        weight,
        pulling_indices,
        expected_grad_centroids,
    )

  @parameterized.parameters(
      ([-1, 1], [[0, 0, 1], [1, 1, 1]], [[-1, -1, 1], [1, 1, 1]]),
      ([-1, 0, 1], [[1, 1, 1], [1, 1, 1]], [[0, 0, 0], [0, 0, 0]]),
  )
  def testDenseWeightsCA(self, clustering_centroids, pulling_indices,
                         expected_output):
    """Verifies that DenseWeightsCA works as expected."""
    clustering_centroids = tf.Variable(clustering_centroids, dtype=tf.float32)
    clustering_algo = clustering_registry.DenseWeightsCA(
        clustering_centroids, GradientAggregation.SUM)
    self._check_pull_values(clustering_algo, pulling_indices, expected_output)

  @parameterized.parameters(
      ([-1, 1], [0, 0, 0, 0, 1], [-1, -1, -1, -1, 1]),
      ([0, 1, 2, 3], [0, 1, 2, 3, 0, 1, 2, 3], [0, 1, 2, 3, 0, 1, 2, 3]),
  )
  def testBiasWeightsCA(self, clustering_centroids, pulling_indices,
                        expected_output):
    """Verifies that BiasWeightsCA works as expected."""
    clustering_centroids = tf.Variable(clustering_centroids, dtype=tf.float32)
    clustering_algo = clustering_registry.BiasWeightsCA(clustering_centroids,
                                                        GradientAggregation.SUM)
    self._check_pull_values(clustering_algo, pulling_indices, expected_output)

  @parameterized.parameters(
      (GradientAggregation.AVG, [[0, 0, 0], [1, 1, 1], [0, 0, 0]], [1, 1]),
      (GradientAggregation.SUM, [[0, 0, 0], [1, 1, 1], [0, 0, 0]], [6, 3]),
      (GradientAggregation.AVG, [[0, 0, 0], [0, 0, 0], [0, 0, 0]], [1, 0]),
      (GradientAggregation.SUM, [[0, 0, 0], [0, 0, 0], [0, 0, 0]], [9, 0]),
  )
  def testConvolutionalWeightsCAGrad(
      self,
      cluster_gradient_aggregation,
      pulling_indices,
      expected_grad_centroids,
  ):
    """Tests that the gradients of ConvolutionalWeightsCA work as expected."""
    clustering_centroids = tf.Variable([0.0, 3.0], dtype=tf.float32)
    weight = tf.constant([[0.1, 0.1, 0.1], [3.0, 3.0, 3.0], [0.2, 0.2, 0.2]])

    clustering_algo = clustering_registry.ConvolutionalWeightsCA(
        clustering_centroids, cluster_gradient_aggregation)
    self._check_gradients_clustered_weight(
        clustering_algo,
        weight,
        pulling_indices,
        expected_grad_centroids,
    )

  @parameterized.parameters(
      ([0, 3], [[[[0, 0, 0], [1, 1, 1], [0, 0, 0]]]], [[[[0, 0, 0], [3, 3, 3],
                                                         [0, 0, 0]]]]),
      ([0, 3, 5], [[[[0, 1, 2], [1, 1, 1], [2, 1, 0]]]
                  ], [[[[0, 3, 5], [3, 3, 3], [5, 3, 0]]]]),
  )
  def testConvolutionalWeightsCA(self, clustering_centroids, pulling_indices,
                                 expected_output):
    """Verifies that ConvolutionalWeightsCA works as expected."""
    clustering_centroids = tf.Variable(clustering_centroids, dtype=tf.float32)
    clustering_algo = clustering_registry.ConvolutionalWeightsCA(
        clustering_centroids, GradientAggregation.SUM)
    self._check_pull_values(clustering_algo, pulling_indices, expected_output)


class CustomLayer(layers.Layer):
  """A custom non-clusterable layer class."""

  def __init__(self, units=10):
    super(CustomLayer, self).__init__()
    self.add_weight(shape=(1, units), initializer='uniform', name='kernel')

  def call(self, inputs):
    return tf.matmul(inputs, self.weights)


class ClusteringLookupRegistryTest(test.TestCase, parameterized.TestCase):
  """Unit tests for the ClusteringLookupRegistry class."""

  def testLookupHasEverythingFromRegistry(self):
    """Verifies ClusteringLookup.

    Every layer that has non-empty ClusteringRegistry records is also presented
    in the ClusteringLookup.
    """
    for layer, clustering_record in ClusterRegistry._LAYERS_WEIGHTS_MAP.items():
      if not clustering_record:
        continue

      self.assertIn(layer, ClusteringLookupRegistry._LAYERS_RESHAPE_MAP)

      for cr in clustering_record:
        self.assertIn(cr, ClusteringLookupRegistry._LAYERS_RESHAPE_MAP[layer])

  def testGetClusteringImplFailsWithUnknonwClassUnknownWeight(self):
    """Verifies that get_clustering_impl() should raise an error.

    when invoked with an unsupported layer class and an unsupported weight
    name.
    """
    with self.assertRaises(ValueError):
      ClusteringLookupRegistry.get_clustering_impl(CustomLayer(),
                                                   'no_such_weight')

  def testGetClusteringImplFailsWithKnonwClassUnknownWeight(self):
    """Verifies that get_clustering_impl() should raise an error.

    when invoked with a supported layer class and an unsupported weight name.
    """
    with self.assertRaises(ValueError):
      ClusteringLookupRegistry.get_clustering_impl(
          layers.Dense(10), 'no_such_weight')


class KerasCustomLayerClusterableInvalid(keras.layers.Layer,
                                         clusterable_layer.ClusterableLayer):
  """Keras custom layer.

  Custom layer derived from ClusterableLayer provides implementation
  of the clustering algorithm.
  """

  def __init__(self, units=10):
    super(KerasCustomLayerClusterableInvalid, self).__init__()
    self.units = units

  def build(self, input_shape):
    self.w = self.add_weight(
        shape=(input_shape[-1], self.units),
        initializer='random_normal',
        trainable=True,
    )

  def get_clusterable_weights(self):
    return [('w', self.w)]

  def testKerasCustomLayerClusterableInvalid(self):
    """Verify get_clustering_impl() raises  error.

    Verify raises error when invoked with a keras custom layer derived from
    ClusterableLayer, but the function get_clustering_algorithm is not provided.
    """
    with self.assertRaises(ValueError):
      ClusteringLookupRegistry.get_clustering_impl(
          KerasCustomLayerClusterableInvalid(), 'w')

  @parameterized.parameters(
      (layers.Conv2D, 'kernel', clustering_registry.ConvolutionalWeightsCA),
      (layers.Conv1D, 'kernel', clustering_registry.ConvolutionalWeightsCA),
      (layers.Conv2D, 'bias', clustering_registry.BiasWeightsCA),
      (layers.Conv1D, 'bias', clustering_registry.BiasWeightsCA),
  )
  def testReturnsResultsForKnownTypeKnownWeights(self, layer_type, weight,
                                                 expected):
    """get_clustering_impl returns the expected clustering lookup algorithm."""
    # layer_type is a class, thus constructing an object here
    self.assertIs(
        ClusteringLookupRegistry.get_clustering_impl(layer_type(32, 3), weight),
        expected)

  def testRegisterNewImplWorks(self):
    """Tests registering a custom clustering lookup algorithm."""

    class NewKernelCA(clustering_registry.AbstractClusteringAlgorithm):

      def get_pulling_indices(self, weight):
        return 1, 2, 3

    new_impl = {CustomLayer: {'new_kernel': NewKernelCA}}

    ClusteringLookupRegistry.register_new_implementation(new_impl)
    self.assertIs(
        ClusteringLookupRegistry.get_clustering_impl(CustomLayer(),
                                                     'new_kernel'), NewKernelCA)

  def testFailsIfNotADictIsGivenAsInput(self):
    """Registering a custom clustering lookup algorithm should fail.

    If the input provided is not a dict.
    """
    with self.assertRaises(TypeError):
      ClusteringLookupRegistry.register_new_implementation([1, 2, 3, 4])

  def testFailsIfNotADictIsGivenAsConcreteImplementation(self):
    """Registering a custom clustering lookup algorithm should fail.

    If the input provided for the concrete implementation is not a dict.
    """
    with self.assertRaises(TypeError):
      ClusteringLookupRegistry.register_new_implementation(
          {ClusteringLookupRegistry: [('new_kernel', lambda x: x)]})


class ClusterRegistryTest(test.TestCase):
  """Unit tests for the ClusteringRegistry class."""

  class CustomLayerFromClusterableLayer(layers.Dense):
    """A custom layer class derived from a built-in clusterable layer."""
    pass

  class CustomLayerFromClusterableLayerNoWeights(layers.Reshape):
    """A custom layer class that does not have any weights.

    Derived from a built-in clusterable layer.
    """
    pass

  class MinimalRNNCell(keras.layers.Layer):
    """A minimal RNN cell implementation."""

    def __init__(self, units, **kwargs):
      self.units = units
      self.state_size = units
      super(ClusterRegistryTest.MinimalRNNCell, self).__init__(**kwargs)

    def build(self, input_shape):
      self.kernel = self.add_weight(
          shape=(input_shape[-1], self.units),
          initializer='uniform',
          name='kernel')
      self.recurrent_kernel = self.add_weight(
          shape=(self.units, self.units),
          initializer='uniform',
          name='recurrent_kernel')
      self.built = True

    def call(self, inputs, states):
      prev_output = states[0]
      h = k.dot(inputs, self.kernel)
      output = h + k.dot(prev_output, self.recurrent_kernel)
      return output, [output]

  class MinimalRNNCellClusterable(MinimalRNNCell,
                                  clusterable_layer.ClusterableLayer):
    """A clusterable minimal RNN cell implementation."""

    def get_clusterable_weights(self):
      return [('kernel', self.kernel),
              ('recurrent_kernel', self.recurrent_kernel)]

  def testSupportsKerasClusterableLayer(self):
    """ClusterRegistry should support a built-in clusterable layer."""
    self.assertTrue(ClusterRegistry.supports(layers.Dense(10)))

  def testSupportsKerasClusterableLayerAlias(self):
    """lusterRegistry should support a built-in clusterable layer alias."""
    # layers.Conv2D maps to layers.convolutional.Conv2D
    self.assertTrue(ClusterRegistry.supports(layers.Conv2D(10, 5)))

  def testSupportsKerasNonClusterableLayer(self):
    """ClusterRegistry should support a built-in non-clusterable layer."""
    # Dropout is a layer known to not be clusterable.
    self.assertTrue(ClusterRegistry.supports(layers.Dropout(0.5)))

  def testDoesNotSupportKerasUnsupportedLayer(self):
    """ClusterRegistry does not support an unknown built-in layer."""
    # ConvLSTM2D is a built-in keras layer but not supported.
    l = layers.ConvLSTM2D(2, (5, 5))
    # We need to build weights
    l.build(input_shape=(10, 10))
    self.assertFalse(ClusterRegistry.supports(l))

  def testSupportsKerasRNNLayers(self):
    """ClusterRegistry should support the expected built-in RNN layers."""
    self.assertTrue(ClusterRegistry.supports(layers.LSTM(10)))
    self.assertTrue(ClusterRegistry.supports(layers.GRU(10)))
    self.assertTrue(ClusterRegistry.supports(layers.SimpleRNN(10)))

  def testDoesNotSupportKerasRNNLayerUnknownCell(self):
    """ClusterRegistry does not support a custom non-clusterable RNN cell."""
    l = keras.layers.RNN(ClusterRegistryTest.MinimalRNNCell(32))
    # We need to build it to have weights
    l.build((10, 1))
    self.assertFalse(ClusterRegistry.supports(l))

  def testSupportsKerasRNNLayerClusterableCell(self):
    """ClusterRegistry should support a custom clusterable RNN cell."""
    self.assertTrue(
        ClusterRegistry.supports(
            keras.layers.RNN(
                ClusterRegistryTest.MinimalRNNCellClusterable(32))))

  def testDoesNotSupportCustomLayer(self):
    """ClusterRegistry does not support a custom non-clusterable layer."""
    self.assertFalse(ClusterRegistry.supports(CustomLayer(10)))

  def testDoesNotSupportCustomLayerInheritedFromClusterableLayer(self):
    """ClusterRegistry does not support a custom layer.

    When the layer is derived from a clusterable layer and has trainable
    weights.
    """
    custom_layer = ClusterRegistryTest.CustomLayerFromClusterableLayer(10)
    custom_layer.build(input_shape=(10, 10))
    self.assertFalse(ClusterRegistry.supports(custom_layer))

  def testSupportsCustomLayerInheritedFromClusterableLayerNoWeights(self):
    """ClusterRegistry should support a custom layer.

    When the layer is derived from a clusterable layer and does not have
    trainable weights.
    """
    custom_layer = (
        ClusterRegistryTest.CustomLayerFromClusterableLayerNoWeights((7, 1)))
    custom_layer.build(input_shape=(3, 4))
    self.assertTrue(ClusterRegistry.supports(custom_layer))

  def testMakeClusterableRaisesErrorForKerasUnsupportedLayer(self):
    """make_clusterable() cannot make layer clusterable.

    When the layer is an unsupported built-in layer.
    """
    l = layers.ConvLSTM2D(2, (5, 5))
    l.build(input_shape=(10, 10))
    with self.assertRaises(ValueError):
      ClusterRegistry.make_clusterable(l)

  def testMakeClusterableRaisesErrorForCustomLayer(self):
    """make_clusterable() cannot make layer clusterable.

    When the layer is a custom non-clusterable layer.
    """
    with self.assertRaises(ValueError):
      ClusterRegistry.make_clusterable(CustomLayer(10))

  def testMakeClusterableRaisesErrorForCustomLayerInheritedFromClusterableLayer(
      self):
    """make_clusterable() cannot make layer clusterable.

    When the layer is a non-clusterable layer derived from a clusterable
    layer.
    """
    l = ClusterRegistryTest.CustomLayerFromClusterableLayer(10)
    l.build(input_shape=(10, 10))
    with self.assertRaises(ValueError):
      ClusterRegistry.make_clusterable(l)

  def testMakeClusterableWorksOnKerasClusterableLayer(self):
    """make_clusterable() makes a built-in clusterable layer clusterable."""
    layer = layers.Dense(10)
    with self.assertRaises(AttributeError):
      layer.get_clusterable_weights()

    ClusterRegistry.make_clusterable(layer)
    # Required since build method sets up the layer weights.
    keras.Sequential([layer]).build(input_shape=(10, 1))

    self.assertEqual([('kernel', layer.kernel)],
                     layer.get_clusterable_weights())

  def testMakeClusterableWorksOnKerasNonClusterableLayer(self):
    """make_clusterable() makes a built-in non-clusterable layer clusterable."""
    layer = layers.Dropout(0.5)
    with self.assertRaises(AttributeError):
      layer.get_clusterable_weights()

    ClusterRegistry.make_clusterable(layer)

    self.assertEqual([], layer.get_clusterable_weights())

  def testMakeClusterableWorksOnKerasRNNLayer(self):
    """make_clusterable() makes a built-in RNN layer clusterable."""
    layer = layers.LSTM(10)
    with self.assertRaises(AttributeError):
      layer.get_clusterable_weights()

    ClusterRegistry.make_clusterable(layer)
    keras.Sequential([layer]).build(input_shape=(2, 3, 4))

    expected_weights = [('kernel', layer.cell.kernel),
                        ('recurrent_kernel', layer.cell.recurrent_kernel)]
    self.assertEqual(expected_weights, layer.get_clusterable_weights())

  def testMakeClusterableWorksOnKerasRNNLayerWithRNNCellsParams(self):
    """A built-in RNN layer with built-in RNN cells is clusterable."""
    cell1 = layers.LSTMCell(10)
    cell2 = layers.GRUCell(5)
    layer = layers.RNN([cell1, cell2])
    with self.assertRaises(AttributeError):
      layer.get_clusterable_weights()

    ClusterRegistry.make_clusterable(layer)
    keras.Sequential([layer]).build(input_shape=(2, 3, 4))

    expected_weights = [('kernel', cell1.kernel),
                        ('recurrent_kernel', cell1.recurrent_kernel),
                        ('kernel', cell2.kernel),
                        ('recurrent_kernel', cell2.recurrent_kernel)]
    self.assertEqual(expected_weights, layer.get_clusterable_weights())

  def testMakeClusterableWorksOnKerasRNNLayerWithClusterableCell(self):
    """A built-in RNN layer with custom clusterable RNN cell is clusterable."""
    cell1 = layers.LSTMCell(10)
    cell2 = ClusterRegistryTest.MinimalRNNCellClusterable(5)
    layer = layers.RNN([cell1, cell2])
    with self.assertRaises(AttributeError):
      layer.get_clusterable_weights()

    ClusterRegistry.make_clusterable(layer)
    keras.Sequential([layer]).build(input_shape=(2, 3, 4))

    expected_weights = [('kernel', cell1.kernel),
                        ('recurrent_kernel', cell1.recurrent_kernel),
                        ('kernel', cell2.kernel),
                        ('recurrent_kernel', cell2.recurrent_kernel)]
    self.assertEqual(expected_weights, layer.get_clusterable_weights())

  def testMakeClusterableRaisesErrorOnRNNLayersUnsupportedCell(self):
    """Verifies that make_clusterable() raises an exception.

    When invoked with a built-in RNN layer that contains a non-clusterable
    custom RNN cell.
    """
    l = ClusterRegistryTest.MinimalRNNCell(5)
    # we need to build weights
    l.build(input_shape=(10, 1))
    with self.assertRaises(ValueError):
      ClusterRegistry.make_clusterable(layers.RNN([layers.LSTMCell(10), l]))


if __name__ == '__main__':
  test.main()
