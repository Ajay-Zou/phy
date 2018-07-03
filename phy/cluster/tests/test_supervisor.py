# -*- coding: utf-8 -*-

"""Test GUI component."""

#------------------------------------------------------------------------------
# Imports
#------------------------------------------------------------------------------

from contextlib import contextmanager

from pytest import yield_fixture, fixture
import numpy as np
from numpy.testing import assert_array_equal as ae

from .. import supervisor as _supervisor
from ..supervisor import (Supervisor,
                          ActionFlow,
                          ClusterView,
                          SimilarityView,
                          ActionCreator,
                          )
from phy.io import Context
from phy.gui import GUI
from phy.gui.widgets import Barrier
from phy.gui.qt import qInstallMessageHandler
#from phy.gui.tests.test_qt import _block
from phy.gui.tests.test_widgets import _assert, _wait_until_table_ready
from phy.utils import connect


def handler(msg_type, msg_log_context, msg_string):
    pass


qInstallMessageHandler(handler)


#------------------------------------------------------------------------------
# Fixtures
#------------------------------------------------------------------------------

@yield_fixture
def gui(tempdir, qtbot):
    # NOTE: mock patch show box exec_
    _supervisor._show_box = lambda _: _

    gui = GUI(position=(200, 100), size=(500, 500), config_dir=tempdir)
    gui.show()
    qtbot.waitForWindowShown(gui)
    yield gui
    qtbot.wait(5)
    gui.close()
    del gui
    qtbot.wait(5)


@fixture
def supervisor(qtbot, gui, cluster_ids, cluster_groups,
               quality, similarity,
               tempdir):
    spike_clusters = np.repeat(cluster_ids, 2)

    mc = Supervisor(spike_clusters,
                    cluster_groups=cluster_groups,
                    quality=quality,
                    similarity=similarity,
                    context=Context(tempdir),
                    )
    mc.attach(gui)
    b = Barrier()
    mc.cluster_view.connect_(b('cluster_view'), event='ready')
    mc.similarity_view.connect_(b('similarity_view'), event='ready')
    b.wait()
    return mc


@contextmanager
def wait_after_event(supervisor, event):
    b = Barrier()
    supervisor.connect(b(1), event=event)
    yield
    b.wait()
    print("Finished waiting after", event)


#------------------------------------------------------------------------------
# Test action flow
#------------------------------------------------------------------------------

def test_action_flow_1():
    assert ActionFlow()._previous_state(None) is None


def test_action_flow_2():
    af = ActionFlow()
    af.update_current_state(cluster_ids=[0])
    assert af.current().cluster_ids == [0]


def test_action_flow_3():
    af = ActionFlow()

    af.add_state(cluster_ids=[0], similar=[100], next_similar=101)
    assert af.current().next_cluster is None

    af.update_current_state(next_cluster=1000)
    assert af.current().next_cluster == 1000

    af.update_current_state(cluster_ids=[1])
    assert af.current().cluster_ids == [0]


def test_action_flow_merge():
    af = ActionFlow()
    af.add_state(cluster_ids=[0], similar=[100], next_cluster=2, next_similar=101)
    af.add_merge(cluster_ids=[0, 100], to=1000)

    s = af.current()
    assert s.type == 'state'
    assert s.cluster_ids == [1000]
    assert s.similar == [101]

    af.add_undo()
    su = af.current()
    assert su.type == 'state'
    assert su.cluster_ids == [0]
    assert su.similar == [100]
    assert su.next_cluster == 2
    assert su.next_similar == 101

    af.add_redo()
    assert af.current() == s


def test_action_flow_split():
    af = ActionFlow()
    af.add_state(cluster_ids=[0], similar=[100], next_cluster=2, next_similar=101)
    af.add_split(old_cluster_ids=[0, 100], new_cluster_ids=[1000, 1001])

    s = af.current()
    assert s.type == 'state'
    assert s.cluster_ids == [1000, 1001]
    assert s.similar is None


def test_action_flow_move_clusters_1():
    af = ActionFlow()
    af.add_state(cluster_ids=[0], similar=[100], next_cluster=2, next_similar=101)
    af.add_move(cluster_ids=[0], group='good')

    s = af.current()
    assert s.type == 'state'
    assert s.cluster_ids == [2]
    # No connection to request_next_similar, so no next similar cluster.
    assert s.similar is None


def test_action_flow_move_clusters_2():
    af = ActionFlow()

    af.add_state(cluster_ids=[0], similar=[100], next_cluster=2, next_similar=101)
    af.add_move(cluster_ids=[0], group='good')

    s = af.current()
    assert s.type == 'state'
    assert s.cluster_ids == [2]
    assert s.similar is None


def test_action_flow_move_similar():
    af = ActionFlow()
    af.add_state(cluster_ids=[0], similar=[100], next_cluster=2, next_similar=101)
    af.add_move(cluster_ids=[100], group='good')

    s = af.current()
    assert s.type == 'state'
    assert s.cluster_ids == [0]
    assert s.similar == [101]


#------------------------------------------------------------------------------
# Test cluster and similarity views
#------------------------------------------------------------------------------

@fixture
def data():
    _data = [{"id": i,
              "n_spikes": 100 - 10 * i,
              "quality": 100 - 10 * i,
              "group": {2: 'noise', 3: 'noise', 5: 'mua', 8: 'good'}.get(i, None),
              "is_masked": i in (2, 3, 5),
              } for i in range(10)]
    return _data


def test_cluster_view_1(qtbot, gui, data):
    cv = ClusterView(gui, data=data)
    _wait_until_table_ready(qtbot, cv)

    cv.sort_by('n_spikes', 'asc')
    _assert(cv.get_state, {'current_sort': ('n_spikes', 'asc')})

    cv.set_state({'current_sort': ('id', 'desc')})
    _assert(cv.get_state, {'current_sort': ('id', 'desc')})


def test_similarity_view_1(qtbot, gui, data):
    sv = SimilarityView(gui, data=data)
    _wait_until_table_ready(qtbot, sv)

    @sv.connect_
    def on_request_similar_clusters(cluster_id):
        return [{'id': id} for id in (100 + cluster_id, 110 + cluster_id, 102 + cluster_id)]

    sv.reset([5])
    _assert(sv.get_ids, [105, 115, 107])


def test_cluster_view_extra_columns(qtbot, gui, data):

    @connect
    def on_request_cluster_metrics(_):
        return ['my_metrics']

    for cl in data:
        cl['my_metrics'] = cl['id'] * 1000

    cv = ClusterView(gui, data=data)
    _wait_until_table_ready(qtbot, cv)


#------------------------------------------------------------------------------
# Test ActionCreator
#------------------------------------------------------------------------------

def test_action_creator_1(qtbot, gui):
    ac = ActionCreator()
    ac.attach(gui)
    gui.show()


#------------------------------------------------------------------------------
# Test GUI component
#------------------------------------------------------------------------------

def _select(supervisor, cluster_ids, similar=None):

    with wait_after_event(supervisor, 'select_clusters_done'):
        supervisor.cluster_view.select(cluster_ids)

    if similar:
        with wait_after_event(supervisor, 'select_similar_done'):
            supervisor.similarity_view.select(similar)

    state = supervisor.action_flow.current()
    assert state.cluster_ids == cluster_ids
    if similar:
        assert state.similar == similar


def _assert_selected(supervisor, sel):
    assert supervisor.selected() == sel


@contextmanager
def wait_selected(supervisor, sel):
    with wait_after_event(supervisor, 'select_clusters_done'):
        yield
    _assert_selected(supervisor, sel)


def test_select(qtbot, supervisor):
    _select(supervisor, [30], [20])
    _assert_selected(supervisor, [30, 20])


def test_supervisor_select_1(qtbot, supervisor):
    with wait_selected(supervisor, [0]):
        supervisor.cluster_view.select([0])


def test_supervisor_select_2(qtbot, supervisor):
    with wait_selected(supervisor, [30]):
        supervisor.cluster_view.next()


def test_supervisor_select_order(qtbot, supervisor):
    with wait_selected(supervisor, [1, 0]):
        supervisor.select([1, 0])
    with wait_selected(supervisor, [0, 1]):
        supervisor.select([0, 1])


def test_supervisor_edge_cases(supervisor):

    # Empty selection at first.
    ae(supervisor.clustering.cluster_ids, [0, 1, 2, 10, 11, 20, 30])

    with wait_selected(supervisor, [0]):
        supervisor.select([0])

    supervisor.undo()
    supervisor.redo()

    # Merge.
    supervisor.merge()
    _assert_selected(supervisor, [0])

    supervisor.merge([])
    _assert_selected(supervisor, [0])

    supervisor.merge([10])
    _assert_selected(supervisor, [0])

    # Split.
    supervisor.split([])
    _assert_selected(supervisor, [0])

    # Move.
    supervisor.move('ignored', [])

    supervisor.save()


def test_supervisor_skip(qtbot, gui, supervisor):

    # yield [0, 1, 2, 10, 11, 20, 30]
    # #      i, g, N,  i,  g,  N, N
    expected = [30, 20, 11, 2, 1]

    for clu in expected:
        with wait_after_event(supervisor, 'select_clusters_done'):
            supervisor.cluster_view.next()
        _assert_selected(supervisor, [clu])


def test_supervisor_merge_1(qtbot, supervisor):

    _select(supervisor, [30], [20])
    _assert_selected(supervisor, [30, 20])

    supervisor.merge()

    _assert_selected(supervisor, [31, 11])

    supervisor.undo()
    _assert_selected(supervisor, [30, 20])

    supervisor.redo()
    _assert_selected(supervisor, [31, 11])


def test_supervisor_merge_move(qtbot, supervisor):
    """Check that merge then move selects the next cluster in the original
    cluster view, not the updated cluster view."""

    _select(supervisor, [20, 11], [])
    _assert_selected(supervisor, [20, 11])

    with wait_after_event(supervisor, 'select_after_action_done'):
        supervisor.merge()
    _assert_selected(supervisor, [31])
    assert supervisor.action_flow.current().next_cluster == 30

    with wait_after_event(supervisor, 'select_after_action_done'):
        supervisor.move('good', 'all')
    _assert_selected(supervisor, [30])

    with wait_after_event(supervisor, 'select_after_action_done'):
        supervisor.move('good', 'all')
    _assert_selected(supervisor, [2])


def test_supervisor_split_0(supervisor):

    _select(supervisor, [1, 2])
    _assert_selected(supervisor, [1, 2])

    supervisor.split([1, 2])

    _assert_selected(supervisor, [31, 32, 33])

    supervisor.undo()
    _assert_selected(supervisor, [1, 2])

    supervisor.redo()
    _assert_selected(supervisor, [31, 32, 33])


def test_supervisor_split_1(supervisor):

    supervisor.select([1, 2])

    @supervisor.connect
    def on_request_split():
        return [1, 2]

    supervisor.split()
    _assert_selected(supervisor, [31, 32, 33])


def test_supervisor_split_2(gui, quality, similarity):
    spike_clusters = np.array([0, 0, 1])

    supervisor = Supervisor(spike_clusters,
                            similarity=similarity,
                            )
    supervisor.attach(gui)

    b = Barrier()
    supervisor.cluster_view.connect_(b('cluster_view'), event='ready')
    supervisor.similarity_view.connect_(b('similarity_view'), event='ready')
    b.wait()

    supervisor.split([0])
    _assert_selected(supervisor, [2, 3])


def test_supervisor_state(tempdir, qtbot, gui, supervisor):

    cv = supervisor.cluster_view
    assert supervisor.state.cluster_view.current_sort == ('quality', 'desc')

    cv.sort_by('id')
    assert supervisor.state.cluster_view.current_sort == ('id', 'asc')

    cv.set_state({'current_sort': ('n_spikes', 'desc')})
    assert supervisor.state.cluster_view.current_sort == ('n_spikes', 'desc')


def _test_supervisor_label(supervisor):

    _select(supervisor, [20])
    supervisor.label("my_field", 3.14)

    supervisor.save()

    assert 'my_field' in supervisor.fields
    assert supervisor.get_labels('my_field')[20] == 3.14


def test_supervisor_move_1(supervisor):

    _select(supervisor, [20])
    _assert_selected(supervisor, [20])

    assert not supervisor.move('', '')

    with wait_after_event(supervisor, 'select_after_action_done'):
        supervisor.move('noise', 'all')
    _assert_selected(supervisor, [11])

    supervisor.undo()
    _assert_selected(supervisor, [20])

    supervisor.redo()
    _assert_selected(supervisor, [11])


def test_supervisor_move_2(supervisor):

    _select(supervisor, [20], [10])
    _assert_selected(supervisor, [20, 10])

    supervisor.move('noise', 10)
    _assert_selected(supervisor, [20, 2])

    supervisor.undo()
    _assert_selected(supervisor, [20, 10])

    supervisor.redo()
    _assert_selected(supervisor, [20, 2])


#------------------------------------------------------------------------------
# Test shortcuts
#------------------------------------------------------------------------------

def test_supervisor_action_reset(qtbot, supervisor):

    supervisor.actions.select([10, 11])

    with wait_after_event(supervisor, 'wizard_done'):
        supervisor.actions.reset()
    _assert_selected(supervisor, [30])

    with wait_after_event(supervisor, 'wizard_done'):
        supervisor.actions.next()
    _assert_selected(supervisor, [30, 20])

    with wait_after_event(supervisor, 'wizard_done'):
        supervisor.actions.next()
    _assert_selected(supervisor, [30, 11])

    with wait_after_event(supervisor, 'wizard_done'):
        supervisor.actions.previous()
    _assert_selected(supervisor, [30, 20])


def test_supervisor_action_nav(qtbot, supervisor):

    with wait_after_event(supervisor, 'wizard_done'):
        supervisor.actions.reset()
    _assert_selected(supervisor, [30])

    with wait_after_event(supervisor, 'wizard_done'):
        supervisor.actions.next_best()
    _assert_selected(supervisor, [20])

    with wait_after_event(supervisor, 'wizard_done'):
        supervisor.actions.previous_best()
    _assert_selected(supervisor, [30])


def test_supervisor_action_move_1(qtbot, supervisor):

    with wait_after_event(supervisor, 'wizard_done'):
        supervisor.actions.next()
    _assert_selected(supervisor, [30])

    with wait_after_event(supervisor, 'select_after_action_done'):
        supervisor.actions.move_best_to_noise()
    _assert_selected(supervisor, [20])

    with wait_after_event(supervisor, 'select_after_action_done'):
        supervisor.actions.move_best_to_mua()
    _assert_selected(supervisor, [11])

    with wait_after_event(supervisor, 'select_after_action_done'):
        supervisor.actions.move_best_to_good()
    _assert_selected(supervisor, [2])

    supervisor.cluster_meta.get('group', 30) == 'noise'
    supervisor.cluster_meta.get('group', 20) == 'mua'
    supervisor.cluster_meta.get('group', 11) == 'good'


def test_supervisor_action_move_2(supervisor):

    _select(supervisor, [30], [20])
    _assert_selected(supervisor, [30, 20])

    with wait_after_event(supervisor, 'select_after_action_done'):
        supervisor.actions.move_similar_to_noise()
    _assert_selected(supervisor, [30, 11])

    with wait_after_event(supervisor, 'select_after_action_done'):
        supervisor.actions.move_similar_to_mua()
    _assert_selected(supervisor, [30, 2])

    with wait_after_event(supervisor, 'select_after_action_done'):
        supervisor.actions.move_similar_to_good()
    _assert_selected(supervisor, [30, 1])

    supervisor.cluster_meta.get('group', 20) == 'noise'
    supervisor.cluster_meta.get('group', 11) == 'mua'
    supervisor.cluster_meta.get('group', 2) == 'good'


def _test_supervisor_action_move_3(supervisor):

    _select(supervisor, [30], [20])
    _assert_selected(supervisor, [30, 20])

    with wait_after_event(supervisor, 'select_after_action_done'):
        supervisor.actions.move_all_to_noise()
    _assert_selected(supervisor, [11, 2])
    return

    with wait_after_event(supervisor, 'wizard_done'):
        supervisor.next()

    _assert_selected(supervisor, [11, 2])

    with wait_after_event(supervisor, 'select_after_action_done'):
        supervisor.actions.move_all_to_mua()

    _assert_selected(supervisor, [1])

    with wait_after_event(supervisor, 'select_after_action_done'):
        supervisor.actions.move_all_to_good()

    _assert_selected(supervisor, [1])

    supervisor.cluster_meta.get('group', 30) == 'noise'
    supervisor.cluster_meta.get('group', 20) == 'noise'

    supervisor.cluster_meta.get('group', 11) == 'mua'
    supervisor.cluster_meta.get('group', 10) == 'mua'

    supervisor.cluster_meta.get('group', 2) == 'good'
    supervisor.cluster_meta.get('group', 1) == 'good'
