# Workflow recording for the public README

Record from a **real, sanitized Obsidian and VS Code session**. Use `demo/demo_note.md` and the standalone `demo/` project, not a private thesis or Obsidian vault. The final GIF and screenshot must depict actual output.

## Required assets

- `assets/workflow-demo.gif`: about 10–15 seconds, approximately 1000 px wide, ideally under 5 MB. Show Obsidian Shell Commands converting the active note to the clipboard, switch to VS Code to run the SVG-to-PDF helper and show the resulting PDF beside the SVG, paste into `Chapters/Demo.tex`, then compile and show the resulting PDF beside the source. Edit out idle compilation time; do not imply that the converter compiles LaTeX.
- `assets/compiled-example.png`: included. This is the verified demo page and can remain in the README as a static result.
- `assets/workflow.svg`: included. Static explanatory diagram for visitors with animations disabled.

Optional: one screenshot comparing Obsidian input and LaTeX output. Do not crowd the README with redundant configuration screenshots.

## Capture and processing

OBS Studio can capture the screen while switching between Obsidian and VS Code. Capture source at 1920x1080 or another readable resolution, hide notifications/personal files, increase editor font size, and keep the file tree visible during the SVG export. Kdenlive can trim to a short sequence and export `workflow.mp4`.

On Linux, FFmpeg can generate a palette-optimized GIF:

```bash
ffmpeg -i workflow.mp4 -vf "fps=10,scale=1000:-1:flags=lanczos,palettegen" palette.png
ffmpeg -i workflow.mp4 -i palette.png -lavfi "fps=10,scale=1000:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3" assets/workflow-demo.gif
```

Add the GIF to the repository and uncomment the example GIF link near the beginning of `README.md`. Use a relative file path so the animation displays on GitHub. Keep the MP4 and Kdenlive project locally unless you explicitly want to distribute the video source.

Before publishing, check all paths, account names, bibliography entries, and visible desktop content for private material. Do not commit a private `.obsidian` directory or an entire vault.
