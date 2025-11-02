#!/bin/bash
kubectl create namespace recruitment --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f kubernetes/ -n recruitment
echo "MySQL déployé dans namespace 'recruitment'"
echo "Connexion : mysql-service.recruitment.svc.cluster.local:3306"