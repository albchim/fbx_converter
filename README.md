# GLB to Maya Converter

## What it does

Turns a 3D model in **GLB** format into a **Maya project** that is ready to open.

The model comes into Maya with its materials already set up, using the textures that came with
it (color, metallic, roughness and normal). Everything is packed in one folder, so you can move it
or share it with a colleague and the textures will still be found.

## How to use it

You need Autodesk Maya installed on your computer. If you have more than one version, the newest
one is used.

1. Double-click **`convert.bat`**.
2. Select the `.glb` file you want to convert.
3. Choose where to save the result and what to call it (for example `bulldog`).
4. Wait until the window says **Done**. The very first time takes a few minutes because it needs
   to download some components, so please be patient and stay connected to the internet.

## What you get

A folder named after your model, containing:

- `scenes` : the Maya scene. **Open this file in Maya.**
- `sourceimages` : all the textures.
- `assets` : a backup copy of the model as an FBX.

In Maya, use *File > Set Project* and pick this folder, then open the scene.

## Good to know

- Autodesk Maya must be installed in its default location, otherwise the converter can't find it.
