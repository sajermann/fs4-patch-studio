import concurrent.futures

from fsmod import workers

GB = 2 ** 30


def test_plan_uses_all_cores_but_one_and_half_the_memory_by_default():
    assert workers.plan(machine_cores=16, machine_memory=32 * GB) == 15
    assert workers.plan(machine_cores=16, machine_memory=2 * GB) == 3  # 1 GB / 300 MB per worker
    assert workers.plan(cores=4, machine_cores=16, machine_memory=32 * GB) == 4
    assert workers.plan(cores=64, machine_cores=16, machine_memory=32 * GB) == 16  # never more than the machine has
    assert workers.plan(memory_percent=10, machine_cores=16, machine_memory=8 * GB) == 2
    assert workers.plan(cores=0, machine_cores=16, machine_memory=32 * GB) == 1


def test_plan_is_defensive_when_the_machine_does_not_tell():
    assert workers.plan(machine_cores=0, machine_memory=32 * GB) == 1  # unknown cores
    assert workers.plan(machine_cores=1, machine_memory=32 * GB) == 1
    assert workers.plan(machine_cores=2, machine_memory=32 * GB) == 1
    assert workers.plan(machine_cores=16, machine_memory=0) == 1  # unknown memory
    assert workers.plan(machine_cores=16, machine_memory=100 * 2 ** 20) == 1  # too little memory for one


def test_machine_facts_are_read_or_none():
    cores, memory = workers.cpu_cores(), workers.total_memory()
    assert cores is None or cores >= 1
    assert memory is None or memory > 0
    info = workers.describe()
    assert info['workers'] >= 1 and info['default_memory_percent'] == 50


def test_pool_runs_calls_in_workers_and_falls_back_to_this_process(monkeypatch):
    pool = workers.Pool(2)
    try:
        assert [pool.submit(pow, 2, k).result() for k in range(5)] == [1, 2, 4, 8, 16]
    finally:
        pool.shutdown()
    pool = workers.Pool(1)  # one worker: everything here
    assert pool.executor is None and pool.submit(pow, 3, 2).result() == 9

    def no_processes(*a, **k):
        raise OSError('blocked')
    monkeypatch.setattr(concurrent.futures, 'ProcessPoolExecutor', no_processes)
    messages = []
    pool = workers.Pool(4, log_fn=messages.append)
    assert pool.executor is None and pool.submit(pow, 2, 10).result() == 1024
    assert messages and 'single process' in messages[0]


def test_settings_are_brought_into_range():
    assert workers.clamp_cores(None) is None and workers.clamp_memory_percent(None) is None
    assert workers.clamp_cores(20, machine_cores=16) == 16 and workers.clamp_cores(0, machine_cores=16) == 1
    assert workers.clamp_cores(4, machine_cores=None) >= 1
    assert workers.clamp_memory_percent(100) == 90 and workers.clamp_memory_percent(5) == 10
    assert workers.plan(memory_percent=100, machine_cores=64, machine_memory=4 * GB) == 12  # 90% of 4 GB / 300 MB
