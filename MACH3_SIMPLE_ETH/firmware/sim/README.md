# grblHAL simulator tests

grblHAL's [Simulator](https://github.com/grblHAL/Simulator) runs the grblHAL
core - parser, planner, step generation, settings, protocol - on a PC, with
a raw TCP port standing in for the board's Telnet. It tests what the core does
with 8 axes, and the protocol a UI will speak. It does **not** test this board:
not the RP2350 driver, the PIO step generator, the pins or the W5500.

Simulator `91eda77`, grblHAL core `d7aaee3`, built with `-DN_AXIS=8`.
`simulator-test.patch` changes two things for testing only: the step log
prints all N_AXIS axes (it printed X Y Z), and the TCP socket sets
SO_REUSEADDR so runs can follow each other.

    git clone --recurse-submodules https://github.com/grblHAL/Simulator
    cd Simulator && git apply .../simulator-test.patch
    cmake -S . -B build8 -DCMAKE_C_FLAGS=-DN_AXIS=8 && make -C build8
    python3 run_tests.py Simulator/build8/grblHAL_sim
    python3 hold_test.py Simulator/build8/grblHAL_sim 12

`client.py` is the whole protocol a sender needs: send a line, wait for `ok`
or `error:n`; send `?` for a `<State|MPos:...>` report; `!` and `~` for feed
hold and cycle start; `$J=` to jog.

## Results (`results.txt`, three runs)

12 / 12 in each run:

| Test | Result |
|---|---|
| `$I` | `[AXS:8:XYZABCUV]` |
| `$100`-`$107` steps/mm, `$110`-`$117`, `$120`-`$127` | stored and read back for all 8 |
| one `G1` on all 8 axes | lands on target; one planner block holds all 8 step counts |
| coordination | worst spread in progress between axes 0.025 % over 361 samples; all 8 moving within the first 1 % |
| `G2` arc in XY with A and U riding along | X20.000 Y0.000 A180.000 U5.000 |
| `$J=` jog on U and V | U2.500 V-1.500 |
| malformed line | refused, `error:2` |
| feed hold `!`, cycle start `~` | stops, holds position, resumes to the end |
| 135-line program (star outline, Z plunges, A/U/V indexing), streamed | no error, ends where it should |

## Found: steps lost across feed hold (`hold_results.txt`)

Hold a two-axis move (`G1 X200 B100`) and resume it, at twelve different
moments: in **8 of 12** the axis with fewer steps ends 1 to 3 steps short
(B 99.996 or 99.988 instead of 100.000). The dominant axis is always exact.
A default **3-axis** build does the same with X/Y (8 of 10), so it is not the
8-axis configuration.

It is either in the core's resume after a hold or in the simulator's
emulation of the stepper interrupt; the simulator cannot say which. The board
generates steps with the RP2350 driver's PIO code, which is different, so
the check that matters is on hardware: count STEP pulses per axis with a
logic analyser (or a second RP2350) across repeated holds, and compare with
`MPos`. If the board shows it too, it goes to grblHAL as an issue with
`hold_test.py` as the reproduction.
