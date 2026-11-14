set -e

commitHash=$(git rev-parse HEAD)
commitHash="${commitHash:-????????????????????????????????????????}"
buildTime=$(date "+%Y-%m-%d %H:%M:%S")
echo $commitHash > build-info.txt
echo -n $buildTime >> build-info.txt

pyiSeparator="${pyiSeparator:-:}"

pyinstaller \
    --name th06-scarlet-mist \
    --icon icon.ico \
    --onefile \
    --noconsole \
    --clean \
    --log-level WARN \
    --add-data "build-info.txt${pyiSeparator}." \
    --add-data "assets${pyiSeparator}assets" \
    main.py
