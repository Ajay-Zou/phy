# -*- coding: utf-8 -*-

"""Views for Kwik model."""

#------------------------------------------------------------------------------
# Imports
#------------------------------------------------------------------------------

from ...utils.array import get_excerpts
from ...plot.ccg import CorrelogramView
from ...plot.features import FeatureView
from ...plot.waveforms import WaveformView
from ...utils._color import _random_color
from ...stats.ccg import correlograms


#------------------------------------------------------------------------------
# ViewModel for plot views and Kwik model
#------------------------------------------------------------------------------

def _create_view(cls, backend=None):
    if backend in ('pyqt4', None):
        kwargs = {'always_on_top': True}
    else:
        kwargs = {}
    return cls(**kwargs)


class BaseViewModel(object):
    """Used to create views from a model."""
    _view_class = None

    def __init__(self, model, backend=None):
        self._model = model
        self._backend = backend
        self._view = _create_view(self._view_class, backend=backend)

    @property
    def model(self):
        return self._model

    @property
    def view(self):
        return self._view

    def on_open(self):
        """To be overriden."""
        self.view.visual.spike_clusters = self.model.spike_clusters

    def on_cluster(self, up):
        """To be overriden."""
        pass

    def on_select(self, clusters, spikes):
        """To be overriden."""
        pass

    def show(self):
        # self._view.update()
        self._view.show()


class WaveformViewModel(BaseViewModel):
    _view_class = WaveformView

    def on_open(self):
        self.view.visual.spike_clusters = self.model.spike_clusters
        self.view.visual.channel_positions = self.model.probe.positions

    def on_select(self, clusters, spikes):
        self.view.visual.waveforms = self.model.waveforms[spikes]
        self.view.visual.masks = self.model.masks[spikes]
        self.view.visual.spike_ids = spikes
        # TODO: how to choose cluster colors?
        self.view.visual.cluster_colors = [_random_color() for _ in clusters]


class FeatureViewModel(BaseViewModel):
    _view_class = FeatureView

    def on_select(self, clusters, spikes):
        features = self.model.features[spikes, :]

        # WARNING: convert features to a 3D array
        # (n_spikes, n_channels, n_features)
        # because that's what the FeatureView expects currently.
        n_fet = self.model.metadata['nfeatures_per_channel']
        n_channels = self.model.n_channels
        shape = (-1, n_channels, n_fet)
        features = features[:, :n_fet * n_channels].reshape(shape)

        self.view.visual.features = features
        self.view.visual.masks = self.model.masks[spikes]

        # TODO: choose dimensions
        self.view.visual.dimensions = [(0, 0), (0, 1)]

        # *All* spike clusters.
        self.view.visual.spike_clusters = self.model.spike_clusters

        self.view.visual.spike_times = self.model.spike_times[spikes]
        self.view.visual.spike_ids = spikes
        self.view.visual.cluster_colors = [_random_color() for _ in clusters]


class CorrelogramViewModel(BaseViewModel):
    _view_class = CorrelogramView

    def on_select(self, clusters, spikes):
        self.view.visual.clusters_ids = clusters

        def _extract(arr):
            # TODO: user-definable CCG parameters
            return get_excerpts(arr, n_excerpts=100, excerpt_size=100)

        # Extract a subset of the spikes belonging to the selected clusters.
        spikes_subset = _extract(spikes)
        spike_clusters = self.model.spike_clusters[spikes_subset]
        spike_times = self.model.spike_times[spikes_subset]

        # Compute the correlograms.
        ccgs = correlograms(spike_times, spike_clusters,
                            binsize=20, winsize_bins=51)

        # TODO: normalization
        ccgs = ccgs * (1. / float(ccgs.max()))

        self.view.visual.correlograms = ccgs
        self.view.visual.cluster_colors = [_random_color() for _ in clusters]
