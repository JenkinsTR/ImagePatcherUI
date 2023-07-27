# This Python file uses the following encoding: utf-8

import os
import subprocess

def main():
    project_name = "ImagePatcherUI"
    project_root = "K:\\GitHub\\ImagePatcherUI\\ImagePatcherUI"
    venv_dir = os.path.join(project_root, "venv\\Scripts")

    dist_dir = os.path.join(project_root, "dist")
    icon_path = os.path.join(project_root, "images", "imagepatcherui.ico")
    script_path = os.path.join(project_root, "imagepatcherui.py")

    command = [
        os.path.join(venv_dir, "pyinstaller"),
        "--onefile",
        "--windowed",
        f"--name={project_name}",
        f"--distpath={dist_dir}",
        f"-i={icon_path}",
        script_path
    ]

    subprocess.run(command)

if __name__ == "__main__":
    main()
