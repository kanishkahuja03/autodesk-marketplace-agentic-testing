# Validation pipeline: functional testing and speed-up

*P&ID Connector Exporter (Kleen Software) on AutoCAD Plant 3D 2027, three test runs, 16–21 October 2026*

## Where we started

Until mid-October the pipeline could install a Marketplace plug-in, check that it loads in its host application, and uninstall it again. It could not yet answer the question that matters most: **does the plug-in actually do what its documentation promises?**

These three runs show that step being added, and then made faster.

## The three runs at a glance

| | Run 1 – functional test works | Run 2 – faster UI handling | Run 3 – lighter AI reasoning |
|---|---|---|---|
| Date | 16 Oct | 19 Oct | 21 Oct |
| Result | 13 passed, 1 needs review | **14 passed** | 14 passed, 1 failed |
| Export feature run and output checked | yes | yes | yes |
| Test execution (agent on the machine) | 15 min 57 s | 9 min 33 s | **8 min 43 s** |
| Whole run, start to report | 19 min 19 s | 12 min 5 s | **11 min 55 s** |
| Time saved vs Run 1 (test execution) | – | **6 min 24 s (−40 %)** | **7 min 14 s (−45 %)** |

## Run 1: the plug-in's feature is tested, not just its presence

The pipeline now reads the plug-in's user guide, finds the features it describes, and writes a test for each one it can safely run. For this plug-in that is **Export**: "export the entire drawing to a JSON file".

To run it, the agent:
- opens AutoCAD Plant 3D on a **copy** of a sample P&ID project (the original is never touched);
- opens a P&ID drawing in it, presses the plug-in's export button and saves the file to a folder of the test's own;
- leaves the decision to the pipeline: code checks that a file was written, and an independent AI reviewer compares the screenshots and the file's content with what the user guide says.

The export worked and produced a 373 KB JSON file. One of the three documented claims ("assets and lines, image and position data") came back as *needs review*: the reviewer was only shown the beginning of the file, and the asset data starts further in.

We also removed two waits that were costing time in every run: the agent waited almost two minutes for the application window because of a wrong matching rule, and up to five minutes for file dialogs it could not detect.

## Run 2: the agent finds buttons by name instead of reading the whole screen

In Run 1 the slowest part by far was how the agent found things on screen. Before almost every click it took a full "snapshot" of the application's interface, a dump of every element in the window. In AutoCAD Plant 3D with a project open that is around 40,000 characters and **took about 46 seconds each time, twelve times per run**: more than half of all test time.

We added a small set of tools that ask Windows directly for **one element by its name** ("P&ID Drawings", "File name:") and click it or type into it. Each step now takes about **3 seconds instead of 46**. The old screen-reading method is kept as a fallback for anything the new tools cannot find, for example the ribbon toolbar, which AutoCAD draws itself.

We also let the reviewer read the **whole** output file, which settled Run 1's open claim: the export does contain assets, lines, image and position data.

**Saved: 6 min 24 s of test execution.** Opening the project and drawing went from 8 min 53 s to 4 min 8 s, and the export test from 2 min 44 s to 57 s. All 14 tests passed.

## Run 3: less AI "thinking" per step

The remaining time is mostly the AI model deciding its next step, about 3–5 seconds each, around 70 times per run. We lowered the model's reasoning effort for the testing agent and tightened a few instructions (answer dialogs by name, never search the ribbon by name).

**Saved: a further 50 seconds**, about one second per step. The trade-off showed straight away: with less reasoning the agent explored a little less thoroughly. In one test it showed the plug-in's tab without opening the drop-down that holds the export button. The reviewer then saw neither of the names the user guide uses and marked that test as **failed**, which is the correct verdict, because the documentation's names do not match the product (see below).

## What the tests found about the plug-in

- It installs, loads, exports and uninstalls cleanly, and leaves nothing behind.
- **The documentation doesn't match the product.** The user guide talks about a tab "P&ID Exporter" with a button "Export"; the product shows a tab **"P&ID Connector"** and a button **"P&ID exportieren"** in a "Werkzeug" drop-down.
- The plug-in's interface appeared in German on our test machine, while the user guide is in English.

## What's next

- **Settle on a middle reasoning setting.** The lowest setting saved little time and made the agent less thorough; a medium setting should keep Run 2's thoroughness at nearly Run 3's speed.
- **Remove the last avoidable waits**, for example not reading the screen while the application is still busy starting up (that alone cost 78 seconds in Run 3).
- **Target:** test execution of around 6½–7 minutes, a whole run of around 8 minutes, with the same results as Run 2.

Everything above is generic: the pipeline names no particular plug-in or host. What it knows about AutoCAD Plant 3D's screens lives in a separate host description that can be written for any other host.
