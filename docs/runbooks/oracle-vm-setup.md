# Oracle Always Free VM — setup (task T0.6)

Goal: one **Ampere A1** VM with **2 OCPU / 12 GB RAM** (the Always Free limit since June 2026), Ubuntu 24.04 ARM, Docker, ports 80/443 open, SSH by key only.
Time: ~45 min of work; getting A1 capacity can take hours to days.

## 1. Create the account
1. Sign up at https://www.oracle.com/cloud/free/. A card is required for identity verification; Always Free resources aren't charged.
2. **Choose the home region carefully — it can't be changed**, and Always Free compute only runs in the home region. Pick the region closest to your users and to the Supabase region you'll use (e.g. if users are in India: Mumbai or Hyderabad, and the Supabase region in Mumbai).
3. Optional: many users report that upgrading to **Pay As You Go** makes A1 capacity easier to get. Always Free resources stay free after upgrading, but anything beyond them is billed. If you upgrade, **set a budget alert first** (Billing → Budgets → $1 alert).

## 2. Create an SSH key (on your computer)
```bash
ssh-keygen -t ed25519 -f ~/.ssh/doctune_oci -C "doctune-oci"
cat ~/.ssh/doctune_oci.pub      # paste this into Oracle in step 4
```
Never share the private key (`~/.ssh/doctune_oci`).

## 3. Create the network
Menu → **Networking → Virtual cloud networks → Start VCN Wizard → "Create VCN with Internet Connectivity"** → name `doctune-vcn` → defaults → Create.

## 4. Create the VM
Menu → **Compute → Instances → Create instance**
| Field | Value |
|---|---|
| Name | `doctune-vm` |
| Image | **Canonical Ubuntu 24.04** (the aarch64 build is picked automatically for Ampere) |
| Shape | Change shape → **Ampere → VM.Standard.A1.Flex** → **2 OCPUs, 12 GB** |
| Networking | `doctune-vcn`, **public subnet**, **Assign a public IPv4 address: yes** |
| SSH keys | Paste public key → contents of `doctune_oci.pub` |
| Boot volume | Specify a custom size → **100 GB** (the Always Free total is 200 GB) |

Click **Create**.

**"Out of host capacity"?** This is common for A1.
- Try each **availability domain** (AD-1/2/3) in the placement section.
- Retry every few hours; mornings and late nights are often easier.
- Or create it at **1 OCPU / 6 GB** first and resize later (stop the instance, Edit shape, then start it).

## 5. Open ports 80 and 443 (two places)
**a) Oracle firewall:** Networking → VCN `doctune-vcn` → Security Lists → Default → **Add Ingress Rules**:
- Source `0.0.0.0/0`, TCP, destination port **80**
- Source `0.0.0.0/0`, TCP, destination port **443**
- Edit the existing port-22 rule: change the source to **your IP/32** instead of `0.0.0.0/0`.

**b) Ubuntu's own iptables** (Oracle's Ubuntu images block these ports by default). After SSHing in (step 6):
```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```
Don't enable `ufw` on top of this; Oracle images use iptables rules, and mixing the two causes lockouts.

## 6. Connect
Copy the **Public IP** from the instance page.
```bash
ssh -i ~/.ssh/doctune_oci ubuntu@<PUBLIC_IP>
```

## 7. Base setup (run on the VM)
```bash
# updates + automatic security updates
sudo apt update && sudo apt -y upgrade
sudo apt -y install unattended-upgrades fail2ban git htop
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

# 4 GB swap (safety net for the 12 GB budget)
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Docker (official script, supports arm64)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
sudo tee /etc/docker/daemon.json >/dev/null <<'JSON'
{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "5" } }
JSON
sudo systemctl restart docker

# SSH hardening: keys only
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart ssh
exit   # log out and back in so the docker group applies
```

## 8. Verify
```bash
ssh -i ~/.ssh/doctune_oci ubuntu@<PUBLIC_IP>
nproc                       # 2
free -h                     # ~11 Gi total, 4 Gi swap
uname -m                    # aarch64
docker run --rm hello-world # works without sudo
docker run -d --name test -p 80:80 nginx:alpine
```
Open `http://<PUBLIC_IP>` in a browser and confirm you see the nginx page. Then remove the test container: `docker rm -f test`.

## 9. Keep the instance
- The public IP stays for the life of the instance; avoid **terminating** it (stopping is fine).
- Idle reclamation only happens if CPU, network **and** memory are all below 20% for 7 days. With DocTune running, memory alone stays above that.
- Make a **boot volume backup** once set up: Block Storage → Boot Volumes → Create backup.

## 10. Report back (no secrets)
Send: region, public IP, `nproc`, `free -h`, and whether the nginx page loaded. **Never send the private key.**
Next steps after this: DNS name + Caddy TLS (T0.6), then the docker-compose stack (`docs/plan/08-infra-devops.md §3`).
