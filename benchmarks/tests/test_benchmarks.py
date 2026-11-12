"""Correctness tests for the benchmark lab (no timing assertions)."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/scripts"))
import bench  # noqa: E402

ZEN = ROOT / "zen/compiler/target/release/zen"
EXPECTED = {
    "arith": "385904853",
    "collatz": "62134795",
    "mem": "2139062878",
    "sort": "14559707269027860169",
}


class HarnessStatsTests(unittest.TestCase):
    def test_summarize_median_min_mean_stdev(self):
        summary = bench.summarize([30, 10, 20, 40])
        self.assertEqual(summary["median_ns"], 25)
        self.assertEqual(summary["min_ns"], 10)
        self.assertEqual(summary["mean_ns"], 25.0)
        self.assertGreater(summary["stdev_ns"], 0)

    def test_summarize_single_sample_has_zero_stdev(self):
        summary = bench.summarize([7])
        self.assertEqual(summary["median_ns"], 7)
        self.assertEqual(summary["stdev_ns"], 0)

    def test_every_benchmark_has_all_language_sources(self):
        for name, spec in bench.BENCHMARKS.items():
            for lang in bench.LANGS:
                self.assertIn(lang, spec, f"{name} lacks {lang}")
                self.assertTrue((ROOT / spec[lang]).is_file(), f"missing {spec[lang]}")


class ChecksumParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ZEN.exists():
            raise unittest.SkipTest(f"build the release compiler first: {ZEN}")

    def _run(self, command):
        return subprocess.run(command, capture_output=True, text=True, check=True, timeout=120).stdout.strip()

    def test_zen_and_c_agree_on_every_benchmark(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for name, spec in bench.BENCHMARKS.items():
                with self.subTest(benchmark=name):
                    zen_out = tmp / f"zen-{name}"
                    c_out = tmp / f"c-{name}"
                    subprocess.run(
                        [str(ZEN), "build", str(ROOT / spec["zen"]), "--release", "-o", str(zen_out)],
                        check=True, capture_output=True, timeout=120)
                    subprocess.run(
                        ["cc", "-std=c11", "-O2", "-o", str(c_out), str(ROOT / spec["c"])],
                        check=True, capture_output=True, timeout=120)
                    zen_text = self._run([str(zen_out)])
                    c_text = self._run([str(c_out)])
                    self.assertEqual(zen_text, c_text, f"checksum mismatch for {name}")
                    self.assertEqual(c_text, EXPECTED[name], f"unexpected checksum for {name}")

    def test_cpp_and_rust_agree_when_toolchains_available(self):
        compilers = {"cpp": ["g++", "-std=c++17", "-O2"], "rust": ["rustc", "-O"]}
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for name, spec in bench.BENCHMARKS.items():
                c_out = tmp / f"c-{name}"
                subprocess.run(["cc", "-std=c11", "-O2", "-o", str(c_out), str(ROOT / spec["c"])],
                               check=True, capture_output=True, timeout=120)
                reference = self._run([str(c_out)])
                for lang, prefix in compilers.items():
                    if not bench.shutil.which(prefix[0]):
                        self.fail(f"missing toolchain '{prefix[0]}' required by the benchmark suite")
                    with self.subTest(benchmark=name, language=lang):
                        output = tmp / f"{lang}-{name}"
                        subprocess.run([*prefix, "-o", str(output), str(ROOT / spec[lang])],
                                       check=True, capture_output=True, timeout=120)
                        self.assertEqual(self._run([str(output)]), reference,
                                         f"checksum mismatch for {lang}/{name}")


class ChecksumAbortTests(unittest.TestCase):
    def test_harness_aborts_before_timing_when_checksums_differ(self):
        if not ZEN.exists():
            raise unittest.SkipTest(f"build the release compiler first: {ZEN}")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            tampered = tmp / "arith_bad.c"
            source = (ROOT / "benchmarks/c/arith.c").read_text().replace(
                'printf("%llu\\n", (unsigned long long)sum);',
                'printf("%llu\\n", (unsigned long long)sum + 1);')
            tampered.write_text(source)
            saved = {k: getattr(bench, k) for k in ("BUILD", "RESULTS", "BENCHMARKS")}
            saved_argv = sys.argv
            try:
                bench.BUILD = tmp / "build"
                bench.RESULTS = tmp / "results"
                bench.BENCHMARKS = {
                    "arith": {**bench.BENCHMARKS["arith"], "c": str(tampered)},
                }
                json_path = tmp / "should-not-exist.json"
                md_path = tmp / "should-not-exist.md"
                sys.argv = ["bench.py", "--reps", "1", "--warmup", "0", "--filter", "arith",
                            "--json", str(json_path), "--md", str(md_path)]
                self.assertEqual(bench.main(), 4, "checksum mismatch must abort with code 4")
                self.assertFalse(json_path.exists())
                self.assertFalse(md_path.exists())
            finally:
                for key, value in saved.items():
                    setattr(bench, key, value)
                sys.argv = saved_argv


if __name__ == "__main__":
    unittest.main()
