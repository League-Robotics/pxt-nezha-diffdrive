"""tests/host/test_gyro_source.py -- SimGyro (sim_gyro.h) and the sensor
configuration probe (src/platform/sensor_config.h) over the host-portable
GyroSource / OpticalPositionSource interfaces (src/platform/gyro_source.h).

Run with::

    uv run pytest tests/host/test_gyro_source.py
"""

import ctypes
import math
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent

OK, FAILED, STALE = 0, 1, 2
OPTICAL, GYRO_ONLY, ENCODERS_ONLY = 0, 1, 2

@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory,
        sources=[_TEST_DIR / "sensor_config_shim.cpp"],
        out_name="libsensor_config_shim.so",
    )
    loaded = ctypes.CDLL(str(lib_path))
    vp, f, i = ctypes.c_void_p, ctypes.c_float, ctypes.c_int
    loaded.sgCreate.restype = vp
    loaded.sgDestroy.argtypes = [vp]
    for name in ("sgSetPresent", "sgSetOpticalPresent", "sgSetDropout",
                 "sgSetFreeze", "sgSetReadFail", "sgFailNextReads"):
        getattr(loaded, name).argtypes = [vp, i]
    loaded.sgSetBias.argtypes = [vp, f]
    loaded.sgSetNoise.argtypes = [vp, f]
    loaded.sgSetWander.argtypes = [vp, f, f]
    loaded.sgSetSeed.argtypes = [vp, ctypes.c_uint32]
    loaded.sgAdvance.argtypes = [vp, f, f]
    for name in ("sgRead", "sgProbe", "sgProbeWithoutGyro",
                 "sgProbeWithoutOptical"):
        getattr(loaded, name).argtypes = [vp]
        getattr(loaded, name).restype = i
    for name in ("sgHeading", "sgRate", "sgTrueHeading", "sgBias"):
        getattr(loaded, name).argtypes = [vp]
        getattr(loaded, name).restype = f
    return loaded


@pytest.fixture
def sim(lib):
    handle = lib.sgCreate()
    yield handle
    lib.sgDestroy(handle)


def run(lib, sim, seconds, rate, dt=0.01):
    for _ in range(int(round(seconds / dt))):
        lib.sgAdvance(sim, dt, rate)


def test_ideal_gyro_tracks_the_true_heading(lib, sim):
    run(lib, sim, 2.0, 0.5)
    assert lib.sgRead(sim) == OK
    assert lib.sgHeading(sim) == pytest.approx(1.0, abs=1e-3)
    assert lib.sgRate(sim) == pytest.approx(0.5, abs=1e-6)


def test_constant_bias_integrates_into_heading_error(lib, sim):
    lib.sgSetBias(sim, 0.01)
    run(lib, sim, 10.0, 0.0)
    assert lib.sgRead(sim) == OK
    assert lib.sgHeading(sim) == pytest.approx(0.1, abs=1e-3)
    assert lib.sgRate(sim) == pytest.approx(0.01, abs=1e-6)
    assert lib.sgTrueHeading(sim) == 0.0


def test_wander_swings_the_bias_about_the_constant(lib, sim):
    lib.sgSetBias(sim, 0.01)
    lib.sgSetWander(sim, 0.004, 40.0)
    seen = []
    for _ in range(400):
        lib.sgAdvance(sim, 0.1, 0.0)
        seen.append(lib.sgBias(sim))
    assert max(seen) == pytest.approx(0.014, abs=1e-4)
    assert min(seen) == pytest.approx(0.006, abs=1e-4)


def test_noise_is_zero_mean_with_requested_spread(lib, sim):
    lib.sgSetNoise(sim, 0.02)
    samples = []
    for _ in range(4000):
        lib.sgAdvance(sim, 0.01, 0.0)
        assert lib.sgRead(sim) == OK
        samples.append(lib.sgRate(sim))
    mean = sum(samples) / len(samples)
    spread = math.sqrt(sum((s - mean) ** 2 for s in samples) / len(samples))
    assert abs(mean) < 0.002
    assert spread == pytest.approx(0.02, rel=0.1)


def test_noise_is_reproducible_for_a_seed(lib, sim):
    def trace(seed):
        lib.sgSetSeed(sim, seed)
        lib.sgSetNoise(sim, 0.02)
        out = []
        for _ in range(5):
            lib.sgAdvance(sim, 0.01, 0.0)
            lib.sgRead(sim)
            out.append(lib.sgRate(sim))
        return out

    first = trace(7)
    assert trace(7) == first
    assert trace(8) != first


def test_dropout_reports_stale_and_holds_the_latched_values(lib, sim):
    run(lib, sim, 1.0, 1.0)
    assert lib.sgRead(sim) == OK
    held = lib.sgHeading(sim)
    lib.sgSetDropout(sim, 1)
    run(lib, sim, 1.0, 1.0)
    assert lib.sgRead(sim) == STALE
    assert lib.sgHeading(sim) == held
    lib.sgSetDropout(sim, 0)
    assert lib.sgRead(sim) == OK
    assert lib.sgHeading(sim) == pytest.approx(2.0, abs=1e-3)


def test_freeze_reports_ok_but_never_changes(lib, sim):
    run(lib, sim, 1.0, 1.0)
    assert lib.sgRead(sim) == OK
    held = lib.sgHeading(sim)
    lib.sgSetFreeze(sim, 1)
    run(lib, sim, 1.0, 1.0)
    assert lib.sgRead(sim) == OK
    assert lib.sgHeading(sim) == held
    lib.sgSetFreeze(sim, 0)
    assert lib.sgRead(sim) == OK
    assert lib.sgHeading(sim) == pytest.approx(2.0, abs=1e-3)


def test_read_failure_reports_failed_and_leaves_values(lib, sim):
    run(lib, sim, 1.0, 1.0)
    assert lib.sgRead(sim) == OK
    held = lib.sgHeading(sim)
    run(lib, sim, 1.0, 1.0)
    lib.sgFailNextReads(sim, 2)
    assert lib.sgRead(sim) == FAILED
    assert lib.sgHeading(sim) == held
    assert lib.sgRead(sim) == FAILED
    assert lib.sgRead(sim) == OK
    assert lib.sgHeading(sim) == pytest.approx(2.0, abs=1e-3)
    lib.sgSetReadFail(sim, 1)
    assert lib.sgRead(sim) == FAILED


def test_absent_gyro_never_reads_ok(lib, sim):
    lib.sgSetPresent(sim, 0)
    assert lib.sgRead(sim) == FAILED


@pytest.mark.parametrize(
    "gyro, optical, expected",
    [
        (1, 1, OPTICAL),
        (1, 0, GYRO_ONLY),
        (0, 0, ENCODERS_ONLY),
        (0, 1, ENCODERS_ONLY),
    ],
)
def test_probe_selects_the_configuration(lib, sim, gyro, optical, expected):
    lib.sgSetPresent(sim, gyro)
    lib.sgSetOpticalPresent(sim, optical)
    assert lib.sgProbe(sim) == expected


def test_probe_treats_a_gyro_that_cannot_be_read_as_absent(lib, sim):
    lib.sgSetOpticalPresent(sim, 1)
    lib.sgSetReadFail(sim, 1)
    assert lib.sgProbe(sim) == ENCODERS_ONLY


def test_probe_accepts_a_stale_first_read(lib, sim):
    lib.sgSetDropout(sim, 1)
    assert lib.sgProbe(sim) == GYRO_ONLY


def test_probe_handles_null_sources(lib, sim):
    lib.sgSetOpticalPresent(sim, 1)
    assert lib.sgProbeWithoutGyro(sim) == ENCODERS_ONLY
    assert lib.sgProbeWithoutOptical(sim) == GYRO_ONLY
