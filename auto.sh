#./bin/bash
git add .
git commit -m "auto commit"
git push origin main
git push github HEAD:main
echo "c'est bon"
