"""
Dependency checker and auto-installer for Trading Bot
Reads from requirements.txt and installs missing packages
"""

import subprocess
import sys
import os
import re

def parse_requirements(filename="requirements.txt"):
    """
    Parse requirements.txt and return list of package names.
    Handles versions, comments, and different formats.
    """
    if not os.path.exists(filename):
        print(f"⚠️  {filename} not found")
        return []
    
    packages = []
    with open(filename, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            # Extract package name (before ==, >=, <=, etc.)
            match = re.match(r'^([a-zA-Z0-9_-]+)', line)
            if match:
                package_name = match.group(1)
                # Handle packages with different import names
                import_name = {
                    'python-dotenv': 'dotenv',
                    'beautifulsoup4': 'bs4',
                    'Pillow': 'PIL',
                    'pyyaml': 'yaml',
                }.get(package_name, package_name)
                
                packages.append((package_name, import_name))
    
    return packages

def check_package(import_name):
    """Check if a package can be imported"""
    try:
        __import__(import_name)
        return True
    except ImportError:
        return False

def install_requirements():
    """Install all packages from requirements.txt at once"""
    print("Installing from requirements.txt...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "--quiet"],
            stdout=subprocess.DEVNULL
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error installing requirements: {e}")
        return False

def check_and_install_dependencies(auto_install=True):
    """
    Check dependencies from requirements.txt and install if missing.
    
    Args:
        auto_install: If True, automatically install missing packages
        
    Returns:
        tuple: (all_installed: bool, newly_installed: bool)
    """
    print("=" * 60)
    print("Checking Trading Bot Dependencies".center(60))
    print("=" * 60)
    
    # Parse requirements.txt
    packages = parse_requirements()
    
    if not packages:
        print("⚠️  No packages found in requirements.txt")
        return True, False
    
    # Check each package
    missing_packages = []
    for package_name, import_name in packages:
        if check_package(import_name):
            print(f"✓ {package_name:<25} installed")
        else:
            print(f"✗ {package_name:<25} MISSING")
            missing_packages.append(package_name)
    
    # Handle missing packages
    if missing_packages:
        print(f"\n⚠️  Found {len(missing_packages)} missing package(s)")
        
        if auto_install:
            print("\nInstalling missing packages from requirements.txt...")
            if install_requirements():
                print("✓ All packages installed successfully")
                newly_installed = True
            else:
                print("❌ Installation failed")
                return False, False
        else:
            print("\nTo install missing packages, run:")
            print("  pip install -r requirements.txt")
            return False, False
    else:
        newly_installed = False
    
    print("\n" + "=" * 60)
    if newly_installed:
        print("✓ All dependencies installed!".center(60))
        print("=" * 60)
        print("\n⚠️  New packages were installed.")
        print("Please restart your script to ensure they load properly.\n")
    else:
        print("✓ All dependencies satisfied!".center(60))
        print("=" * 60)
    
    return True, newly_installed

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Check and install trading bot dependencies")
    parser.add_argument("--no-install", action="store_true", 
                       help="Only check dependencies, don't install")
    parser.add_argument("--list", action="store_true",
                       help="List all packages in requirements.txt")
    
    args = parser.parse_args()
    
    if args.list:
        print("Packages in requirements.txt:")
        packages = parse_requirements()
        for pkg_name, import_name in packages:
            print(f"  - {pkg_name} (imports as: {import_name})")
    else:
        all_ok, installed = check_and_install_dependencies(auto_install=not args.no_install)
        
        if not all_ok:
            sys.exit(1)
        elif installed:
            sys.exit(2)  # Signal that restart is needed