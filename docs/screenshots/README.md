# Screenshots

The main README embeds images from this folder. They are the single highest-value
thing you can add to this repo — most people decide whether to keep reading based
on the first image, not the prose.

## What to capture

Save each as a PNG with exactly these names so the README picks them up:

| Filename | What it should show |
| --- | --- |
| `main-window.png` | The whole app after a successful run: prompt on the left, the generated solid in the viewer on the right, log console showing the attempts |
| `text-to-part.gif` | A short loop — type a prompt, hit generate, model appears. 10–15 seconds is plenty |
| `retry-loop.png` | The log console on a run where attempt 1 failed and attempt 2 succeeded. This is the most interesting thing the project does and it is invisible in a static screenshot of a finished model |
| `pdf-input.png` | A PDF drawing loaded in the input panel next to the resulting geometry |

## Tips

- Use a prompt that produces something recognisable — a flange or a bracket reads
  better than a cube.
- Crop tightly. Do not include your desktop, taskbar, or filenames from your machine.
- **Check what is on screen before you publish it.** Window titles, recent-file
  lists, and folder paths in the file dialog all leak into screenshots.
- For the GIF, [ScreenToGif](https://www.screentogif.com/) (Windows) is free and
  exports small files. Keep it under about 5 MB.

## Adding them to the README

`main-window.png` is already referenced near the top. Add the others where they
fit — the retry-loop capture belongs next to the "Why this is harder than 'ask an
LLM for code'" table, since that is exactly what it illustrates.
