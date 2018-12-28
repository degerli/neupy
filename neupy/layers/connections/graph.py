import copy
import pprint
import inspect
from collections import OrderedDict

import six

from neupy.exceptions import LayerConnectionError


__all__ = ('LayerGraph',)


def filter_dict(dictionary, include_keys):
    """
    Create new list that contains only values
    specified in the ``include_keys`` attribute.

    Parameters
    ----------
    dictionary : dict
        Original dictionary

    include_keys : list or tuple
        Keys that will copied from original dictionary
        into a new one.

    Returns
    -------
    dict
    """
    filtered_dict = OrderedDict()

    for key, value in dictionary.items():
        if key in include_keys:
            filtered_dict[key] = [v for v in value if v in include_keys]

    return filtered_dict


def is_cyclic(graph):
    """
    Check if graph has cycles.

    Parameters
    ----------
    graph : dict
        must be represented as a dictionary mapping vertices to
        iterables of neighbouring vertices.

    Returns
    -------
    bool
        Return ``True`` if the directed graph has a cycle.

    Examples
    --------
    >>> is_cyclic({1: (2,), 2: (3,), 3: (1,)})
    True
    >>> is_cyclic({1: (2,), 2: (3,), 3: (4,)})
    False
    """
    path = set()
    visited = set()

    def visit(vertex):
        if vertex in visited:
            return False

        visited.add(vertex)
        path.add(vertex)

        for neighbour in graph.get(vertex, ()):
            if neighbour in path or visit(neighbour):
                return True

        path.remove(vertex)
        return False

    return any(visit(vertex) for vertex in graph)


def does_layer_expect_one_input(layer):
    """
    Check whether layer can except only one input layer.

    Parameters
    ----------
    layer : layer or connection

    Raises
    ------
    ValueError
        In case if argument is not a layer.

    Retruns
    -------
    bool
        Returns ``True`` if layer can accept onl one input
        layer, ``False`` otherwise.
    """
    if not hasattr(layer, 'output'):
        raise ValueError(
            "Layer `{}` doesn't have output method".format(layer))

    if not inspect.ismethod(layer.output):
        raise ValueError(
            "Layer has an `output` property, but it's not a method")

    # The main output method overwrapped with decoretor that destroys
    # original properties of the method. The original method can be found
    # in the `original_method` attribute
    arginfo = inspect.getargspec(layer.output.original_method)

    if arginfo.varargs is not None:
        return False

    # In case if layer expects fixed number of input layers
    n_args = len(arginfo.args) - 1  # Ignore `self` argument
    return n_args == 1


class LayerGraph(object):
    """
    Direct Acyclic Graph (DAG) for layer connections.

    Parameters
    ----------
    forward_graph : None or dict

    Raises
    ------
    LayerConnectionError
        If graph cannot connect layers.
    """
    def __init__(self, forward_graph=None):
        self.forward_graph = forward_graph or OrderedDict()

    @classmethod
    def merge(cls, left_graph, right_graph):
        """
        Combine two separated graphs into one.

        Parameters
        ----------
        left_graph : LayerGraph instance
        right_graph : LayerGraph instance

        Returns
        -------
        LayerGraph instance
            New graph that contains layers and connections
            from input graphs.
        """

        forward_graph = OrderedDict()

        for key, value in left_graph.forward_graph.items():
            # To make sure that we copied lists inside of the
            # dictionary, but didn't copied values inside of the list
            forward_graph[key] = copy.copy(value)

        for key, values in right_graph.forward_graph.items():
            if key in forward_graph:
                for value in values:
                    if value not in forward_graph[key]:
                        forward_graph[key].append(value)
            else:
                forward_graph[key] = copy.copy(values)

        return cls(forward_graph)

    @property
    def backward_graph(self):
        # Make sure that order stays the same
        backward = OrderedDict([(layer, []) for layer in self.forward_graph])

        for to_layer, from_layers in self.forward_graph.items():
            for from_layer in from_layers:
                backward[from_layer].append(to_layer)

        return backward

    def add_layer(self, layer):
        """
        Add new layer into the graph.
        """
        if layer in self.forward_graph:
            return

        for existed_layer in self.forward_graph:
            if existed_layer.name == layer.name:
                raise LayerConnectionError(
                    "Cannot connect {} layer. Layer with name {!r} has been "
                    "already defined in the graph.".format(layer, layer.name))

        self.forward_graph[layer] = []

    def add_connection(self, from_layer, to_layer):
        """
        Add new directional connection between two layers.

        Parameters
        ----------
        from_layer : layer
        to_layer : layer

        Raises
        ------
        LayerConnectionError
            Raises if it's impossible to connect two layers or
            new connection creates cycles in graph.

        Returns
        -------
        bool
            Returns ``False`` if connection has already been added into
            the graph, and ``True`` if connection was added successfully.
        """
        if from_layer is to_layer:
            raise LayerConnectionError(
                "Cannot connect layer `{}` to itself".format(from_layer))

        self.add_layer(from_layer)
        self.add_layer(to_layer)

        if to_layer in self.forward_graph[from_layer]:
            # Layers have been already connected
            return False

        self.forward_graph[from_layer].append(to_layer)

        if is_cyclic(self.forward_graph):
            raise LayerConnectionError(
                "Cannot connect layer `{}` to `{}`, because this "
                "connection creates cycle in the graph."
                "".format(from_layer, to_layer))

        return True

    def connect_layers(self, from_layers, to_layers):
        """
        Connect two layers together and update other layers
        in the graph.

        Parameters
        ----------
        from_layer : layer or list of layers
        to_layer : layer or list of layers

        Raises
        ------
        LayerConnectionError
            Raises if cannot graph cannot connect two layers.

        Returns
        -------
        bool
            Returns ``False`` if connection has already been added into
            the graph, and ``True`` if connection was added successfully.
        """
        if not isinstance(from_layers, (list, tuple)):
            from_layers = [from_layers]

        if not isinstance(to_layers, (list, tuple)):
            to_layers = [to_layers]

        connections_added = []
        do_not_have_shapes = True

        for from_layer in from_layers:
            if from_layer.input_shape or from_layer.output_shape:
                do_not_have_shapes = False

            for to_layer in to_layers:
                connection_added = self.add_connection(from_layer, to_layer)
                connections_added.append(connection_added)

        if not any(connections_added):
            return False

        if do_not_have_shapes:
            return True

        # Layer has an input shape which means that we can
        # propagate this information through the graph and
        # set up input shape for layers that don't have it.
        layers = copy.copy(from_layers)
        forward_graph = self.forward_graph
        backward_graph = self.backward_graph

        # We need to know whether all input layers
        # have defined input shape
        all_inputs_has_shape = all(
            layer.input_shape for layer in self.input_layers)

        while layers:
            current_layer = layers.pop()
            next_layers = forward_graph[current_layer]

            for next_layer in next_layers:
                next_inp_shape = next_layer.input_shape
                current_out_shape = current_layer.output_shape
                expect_one_input = does_layer_expect_one_input(next_layer)

                if not next_inp_shape and expect_one_input:
                    next_layer.input_shape = current_out_shape
                    next_layer.initialize()

                elif not expect_one_input and all_inputs_has_shape:
                    input_shapes = []
                    for incoming_layer in backward_graph[next_layer]:
                        input_shapes.append(incoming_layer.output_shape)

                    if None not in input_shapes:
                        next_layer.input_shape = input_shapes
                        next_layer.initialize()

                    else:
                        # Some of the previous layers still don't
                        # have input shape. We can put layer at the
                        # end of the stack and check it again at the end
                        layers.insert(0, current_layer)

                elif expect_one_input and next_inp_shape != current_out_shape:
                    raise LayerConnectionError(
                        "Cannot connect `{}` to the `{}`. Output shape "
                        "from one layer is equal to {} and input shape "
                        "to the next one is equal to {}".format(
                            current_layer, next_layer,
                            current_out_shape, next_inp_shape,
                        ))

            layers.extend(next_layers)

        return True

    def reverse(self):
        """
        Returns graph with reversed connections.
        """
        return LayerGraph(self.backward_graph)

    def subgraph_for_output(self, output_layers):
        """
        Extract subgraph with specified set
        of output layers.

        Parameters
        ----------
        layers : layer, list of layers

        Returns
        -------
        LayerGraph instance
        """
        if not isinstance(output_layers, (list, tuple)):
            output_layers = [output_layers]

        if all(layer not in self.forward_graph for layer in output_layers):
            return LayerGraph()

        observed_layers = []
        layers = copy.copy(output_layers)
        backward_graph = self.backward_graph

        while layers:
            current_layer = layers.pop()
            observed_layers.append(current_layer)

            for next_layer in backward_graph[current_layer]:
                if next_layer not in observed_layers:
                    layers.append(next_layer)

        forward_subgraph = filter_dict(self.forward_graph, observed_layers)
        # Remove old relations to the other layers.
        # Output layer cannot point to some other layers.
        for layer in output_layers:
            forward_subgraph[layer] = []

        return LayerGraph(forward_subgraph)

    def subgraph_for_input(self, input_layers):
        """
        Extract subgraph with specified set
        of input layers.

        Parameters
        ----------
        layers : layer, list of layers

        Returns
        -------
        LayerGraph instance
        """
        # Output layers for the reversed graph are
        # input layers for normal graph
        graph_reversed = self.reverse()
        subgraph_reversed = graph_reversed.subgraph_for_output(input_layers)

        # Reverse it to make normal graph
        return subgraph_reversed.reverse()

    def subgraph(self, input_layers, output_layers):
        """
        Create subgraph that contains only layers that
        has relations between specified input and output
        layers.

        Parameters
        ----------
        input_layers : layer, list of layers
        output_layers : layer, list of layers

        Returns
        -------
        LayerGraph
        """
        subgraph = self.subgraph_for_input(input_layers)
        return subgraph.subgraph_for_output(output_layers)

    @property
    def input_layers(self):
        """
        List of input layers.

        Raises
        ------
        LayerConnectionError
            If graph doesn't have input layers.

        Returns
        -------
        list
            List of input layers.
        """
        reversed_graph = self.reverse()
        return reversed_graph.output_layers

    @property
    def output_layers(self):
        """
        List of output layers.

        Raises
        ------
        LayerConnectionError
            If graph doesn't have output layers.

        Returns
        -------
        list
            List of output layers.
        """
        output_layers = []

        for layer, next_layers in self.forward_graph.items():
            if not next_layers:
                output_layers.append(layer)

        return output_layers

    def find_layer_by_name(self, layer_name):
        """
        Find layer instance in the graph based on the
        specified layer name.

        Parameters
        ----------
        layer_name : str
            Name of the layer that presented in this graph.

        Raises
        ------
        NameError
            In case if there is no layer with specified
            name in the graph.

        Returns
        -------
        layer
        """
        for layer in self.forward_graph:
            if layer.name == layer_name:
                return layer

        raise NameError("Cannot find layer with name {!r}".format(layer_name))

    def propagate_forward(self, input_value):
        """
        Propagates input variable through the directed acyclic
        graph and returns output from the final layers.

        Parameters
        ----------
        input_value : array-like, Tensorfow variable or dict
          - If input is an array or Tensorfow variable than it will
            be used as a direct input to the input layer/layers.

          - The dict type input should has a specific structure.
            Each key of the dict is a layer and each value array or
            Tensorfow variable. Dict defines input values for specific
            layers. In the dict input layer is not necessary should
            be an instance of the ``layers.Input`` class. It can be
            any layer from the graph.

        Returns
        -------
        object
            Output from the final layer/layers.
        """
        outputs = {}
        backward_graph = self.backward_graph

        if isinstance(input_value, (list, tuple)):
            n_input_layers = len(self.input_layers)
            n_input_vars = len(input_value)

            if n_input_vars != n_input_layers:
                raise ValueError(
                    "Connection has {} input layer(s), but {} inputs was "
                    "provided".format(n_input_layers, n_input_vars))

            # Layers in the self.graph.input_layers and
            # self.input_layers variables can have a different order.
            # Order in the self.input_layers is defined by user
            input_value_as_dict = {}

            for layer, value in zip(self.input_layers, input_value):
                input_value_as_dict[layer] = value

            input_value = input_value_as_dict

        if isinstance(input_value, dict):
            for layer, input_variable in input_value.items():
                if isinstance(layer, six.string_types):
                    layer = self.find_layer_by_name(layer)

                if layer not in self.forward_graph:
                    raise ValueError(
                        "The `{}` layer doesn't appear in the graph"
                        "".format(layer))

                outputs[layer] = layer.output(input_variable)
        else:
            for input_layer in self.input_layers:
                outputs[input_layer] = input_layer.output(input_value)

        def output_from_layer(layer):
            if layer in outputs:
                return outputs[layer]

            input_layers = backward_graph[layer]
            inputs = []
            for input_layer in input_layers:
                if input_layer in outputs:
                    res = outputs[input_layer]
                else:
                    res = output_from_layer(input_layer)
                    outputs[input_layer] = res

                inputs.append(res)

            return layer.output(*inputs)

        results = []
        for output_layer in self.output_layers:
            results.append(output_from_layer(output_layer))

        if len(results) == 1:
            results = results[0]

        return results

    def layer_names_only(self):
        """
        Replaces in the graph layers with their names.

        Parameters
        ----------
        graph : LayerGraph

        Returns
        -------
        OrderedDict
        """
        prepared_graph = OrderedDict()

        for from_layer, to_layers in self.forward_graph.items():
            prepared_graph[from_layer.name] = [l.name for l in to_layers]

        return list(prepared_graph.items())

    def __contains__(self, layer):
        return layer in self.forward_graph

    def __len__(self):
        return len(self.forward_graph)

    def __repr__(self):
        graph = list(self.forward_graph.items())
        return pprint.pformat(graph)
