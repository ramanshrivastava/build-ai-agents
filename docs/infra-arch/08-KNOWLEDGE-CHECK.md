# Kubernetes Knowledge Check — 55+ Questions with Detailed Answers

> **Document 08 of 11** in the [Infrastructure & Kubernetes Learning Guide](./00-OVERVIEW.md)
>
> **Purpose:** Self-assessment and knowledge validation covering the full breadth of Kubernetes — from core concepts through debugging production issues. Every answer is written to be technically thorough and production-ready.
>
> **How to use this document:** Read through each category. For each question, try answering it yourself before reading the provided answer. The "AI Doctor Example" callouts show how abstract concepts map to the concrete AI Doctor Assistant application (FastAPI + React + PostgreSQL + Claude Agent SDK on GKE Autopilot).

---

## Table of Contents

1. [Core Concepts](#1-core-concepts) (Questions 1–8)
2. [Networking](#2-networking) (Questions 9–16)
3. [Storage](#3-storage) (Questions 17–22)
4. [Workloads & Scheduling](#4-workloads--scheduling) (Questions 23–28)
5. [Configuration & Secrets](#5-configuration--secrets) (Questions 29–33)
6. [Scaling](#6-scaling) (Questions 34–38)
7. [GKE-Specific](#7-gke-specific) (Questions 39–43)
8. [Real-World Scenarios](#8-real-world-scenarios) (Questions 44–48)
9. [Security](#9-security) (Questions 49–53)
10. [Debugging & Troubleshooting](#10-debugging--troubleshooting) (Questions 54–58)

---

## 1. Core Concepts

### Q1. What is a Pod and why is it the smallest deployable unit in Kubernetes?

A Pod is the smallest deployable unit in Kubernetes — not a container. A Pod is an abstraction that wraps one or more containers that need to share the same network namespace, the same IPC namespace, and optionally the same storage volumes. Every container in a Pod gets the same IP address and can communicate with sibling containers via `localhost`. They are co-scheduled onto the same node and share the same lifecycle: when a Pod is killed, all of its containers are killed together.

The reason Kubernetes doesn't schedule individual containers is a design decision rooted in real-world application patterns. Many applications require tightly coupled helper processes — log shippers, proxy sidecars, config reloaders — that need to run alongside the main application process. By grouping these into a Pod, Kubernetes guarantees they land on the same node, share networking, and start/stop together. If containers were the scheduling unit, you'd need to build complex affinity rules to keep related containers together, and you'd lose the shared-network guarantee.

In practice, most Pods run a single container. The multi-container pattern is reserved for cases where the sidecar genuinely needs to share the Pod's network or filesystem — like a service mesh proxy (Envoy) intercepting traffic, or a log agent reading from a shared volume. You should not use multi-container Pods simply because two services "talk to each other" — that's what Services are for.

> **AI Doctor Example:** The `doctor-backend` Pod runs a single container with the FastAPI application on port 8000. If we later added Istio for service mesh, an Envoy sidecar container would be injected into the same Pod, intercepting all inbound and outbound traffic. Both containers share the Pod's IP address — Envoy listens on port 15001 and transparently proxies to the FastAPI container on localhost:8000.

### Q2. What is the difference between a Deployment and a ReplicaSet? Why don't you create ReplicaSets directly?

A ReplicaSet ensures that a specified number of Pod replicas are running at any given time. If a Pod dies, the ReplicaSet controller notices (via the control loop watching the API server) and creates a replacement. A ReplicaSet uses label selectors to identify which Pods it manages — it doesn't track Pods by name, but by matching labels.

A Deployment is a higher-level abstraction that manages ReplicaSets. When you create a Deployment, it creates a ReplicaSet behind the scenes. The key value Deployments add is **rollout management**: when you update a Deployment's Pod template (e.g., change the container image), the Deployment creates a *new* ReplicaSet with the updated template and gradually scales it up while scaling the old ReplicaSet down. This is the rolling update mechanism. The Deployment also keeps a history of old ReplicaSets (controlled by `revisionHistoryLimit`), enabling rollbacks with `kubectl rollout undo`.

You don't create ReplicaSets directly because you lose all rollout intelligence. If you update a ReplicaSet's Pod template, existing Pods are not affected — only new Pods created afterward will use the new template. There is no rolling update, no rollback history, no deployment strategy. You'd have to manually manage the transition between old and new Pods, which is exactly what the Deployment controller automates. In nearly all cases, you should use a Deployment. The only time you'd consider a bare ReplicaSet is if you have a custom controller that implements its own rollout strategy.

> **AI Doctor Example:** The `doctor-backend` Deployment specifies `replicas: 2` and uses the `RollingUpdate` strategy. When we push a new backend image (e.g., updating from `v1.0.0` to `v1.1.0`), the Deployment creates a new ReplicaSet with the updated image. It spins up one new Pod, waits for its readiness probe (`/health` on port 8000) to pass, then terminates one old Pod. This repeats until all replicas run the new version. If the new version's health check fails, the rollout stalls and can be rolled back with `kubectl rollout undo deployment/doctor-backend -n doctor-app`.

### Q3. Explain the three types of Kubernetes Services (ClusterIP, NodePort, LoadBalancer). When would you use each?

**ClusterIP** is the default Service type. It assigns a virtual IP address that is only reachable from within the cluster. When a Pod sends traffic to the ClusterIP, kube-proxy (running on every node) intercepts the traffic and load-balances it across the backend Pods matching the Service's selector. ClusterIP is used for internal communication between microservices — for example, a backend talking to a database. The DNS record `my-service.my-namespace.svc.cluster.local` resolves to the ClusterIP.

**NodePort** exposes the Service on a static port (range 30000–32767) on every node's IP address. Traffic arriving at `<NodeIP>:<NodePort>` is forwarded to the Service's ClusterIP, which then routes to a backend Pod. NodePort is useful for development or when you have your own external load balancer that can distribute traffic across node IPs. In production, you rarely use NodePort directly because it exposes high-numbered ports and requires you to manage node IP discovery yourself.

**LoadBalancer** extends NodePort by provisioning a cloud provider's external load balancer (e.g., a GCP Network Load Balancer). The cloud load balancer gets a stable external IP and forwards traffic to the NodePort on each node. This is the simplest way to expose a service externally on a managed Kubernetes platform. The downside is cost: each LoadBalancer Service provisions a separate cloud load balancer, which can get expensive if you have many services. This is why Ingress exists — it consolidates multiple services behind a single load balancer.

There's also **ExternalName**, a less common type that maps a Service to a DNS CNAME record (e.g., pointing to an external database hostname). It doesn't proxy traffic — it just returns a CNAME record from the cluster DNS.

> **AI Doctor Example:** In the AI Doctor cluster, PostgreSQL (`postgres` service in the `doctor-app` namespace) uses **ClusterIP** — it should only be reachable from within the cluster by the backend. The `doctor-backend` Service also uses **ClusterIP** because the Ingress controller routes external `/api/*` traffic to it. The Ingress controller itself is the only component that needs a **LoadBalancer** Service to get an external IP. This means we pay for only one cloud load balancer, not three.

### Q4. What are Namespaces and when should you use them?

Namespaces are a mechanism for dividing a single physical cluster into multiple virtual clusters. They provide a scope for names: two resources can have the same name if they are in different namespaces. Namespaces also serve as the boundary for resource quotas (CPU/memory limits per namespace), RBAC policies, and NetworkPolicies.

Kubernetes comes with several default namespaces: `default` (where resources go if you don't specify a namespace), `kube-system` (control plane components like the scheduler, controller manager, CoreDNS), `kube-public` (readable by all users, mostly unused), and `kube-node-lease` (node heartbeat leases). In production, you should avoid using the `default` namespace because it makes it hard to apply targeted policies and quotas.

You should use namespaces when you need logical isolation between teams, environments (dev/staging/production in the same cluster), or application boundaries. For example, running staging and production in the same cluster with separate namespaces lets you apply different resource quotas and RBAC rules. However, namespaces are not a security boundary on their own — a compromised Pod in one namespace can potentially access another namespace's Pods unless you enforce NetworkPolicies and strict RBAC. For hard multi-tenancy (untrusted workloads), you need more than namespaces — you need separate clusters or technologies like vCluster.

Don't over-namespace. A small team with a single application doesn't need ten namespaces. Use one namespace per logical application boundary, and use labels for finer-grained organization within a namespace.

> **AI Doctor Example:** All AI Doctor components — `doctor-backend`, `doctor-frontend`, `postgres`, ConfigMaps, Secrets, and the Ingress — live in the `doctor-app` namespace. This keeps them isolated from other workloads in the cluster, allows us to set a ResourceQuota limiting the namespace to (say) 4 CPUs and 8Gi of memory, and lets us apply a default NetworkPolicy that denies ingress from other namespaces.

### Q5. What are Labels and Selectors? How do they enable loose coupling?

Labels are key-value pairs attached to Kubernetes objects (Pods, Services, Deployments, Nodes — anything). They are metadata, not unique identifiers. Examples: `app: doctor-backend`, `tier: backend`, `environment: production`. Labels are indexed by the API server, making label-based queries efficient.

Selectors are queries that filter objects by their labels. There are two types: **equality-based** (`app = doctor-backend`) and **set-based** (`environment in (production, staging)`). Services use selectors to find backend Pods, Deployments use selectors to manage their ReplicaSets, and NetworkPolicies use selectors to target specific Pods.

The loose coupling comes from the fact that controllers don't own objects by reference or name — they find them dynamically by label matching. A Service doesn't hardcode the names of its backend Pods; it says "route traffic to any Pod matching `app: doctor-backend`." This means Pods can be created, destroyed, and recreated with different names, and the Service automatically adjusts. Deployments work the same way — the Deployment controller finds its Pods by label, not by a direct pointer. This indirection is what makes Kubernetes self-healing and elastic: controllers continuously reconcile the desired state (expressed via selectors) with the actual state.

Be careful with labels: if two controllers have overlapping selectors (matching the same Pods), they'll fight over the same Pods, causing unpredictable behavior. Always ensure your label combinations are unique per controller.

### Q6. What is a DaemonSet and how does it differ from a Deployment?

A DaemonSet ensures that exactly one copy of a Pod runs on every node in the cluster (or on a subset of nodes, filtered by node selectors or tolerations). When a new node is added to the cluster, the DaemonSet controller automatically schedules a Pod on it. When a node is removed, the Pod is garbage-collected.

A Deployment, in contrast, specifies a desired number of replicas that the scheduler distributes across available nodes. The scheduler chooses which nodes to use based on resource availability, affinity rules, and taints — a Deployment doesn't guarantee one Pod per node, and it doesn't automatically react to nodes joining or leaving (other than the scheduler rescheduling evicted Pods).

DaemonSets are used for node-level infrastructure: log collectors (Fluentd, Filebeat), monitoring agents (Prometheus node-exporter, Datadog agent), network plugins (Calico, Cilium), and storage drivers (CSI node plugins). These are workloads where every node needs one instance — running two on the same node would be wasteful or conflicting, and missing a node means missing data.

In GKE Autopilot, DaemonSets work differently because you don't manage nodes directly. Autopilot provisions nodes dynamically based on Pod requests, and Google manages certain DaemonSet-like functionality (logging, monitoring) at the platform level. You can still create DaemonSets in Autopilot, but they count toward your Pod resource requests and there are some restrictions on privileged workloads.

### Q7. What is the difference between a Job and a CronJob?

A Job creates one or more Pods and ensures a specified number of them successfully complete (exit with code 0). Unlike a Deployment, which keeps Pods running indefinitely, a Job runs to completion. Once the Job's Pods finish successfully, the Job is considered complete and no new Pods are created. If a Pod fails, the Job controller creates a replacement (up to `backoffLimit` retries).

Jobs support parallelism: you can set `completions: 5` and `parallelism: 3` to run 5 total tasks with up to 3 running concurrently. The Job controller manages this queue automatically. Jobs are used for batch work: database migrations, data processing tasks, report generation, backup operations — anything that should run once (or a fixed number of times) and then stop.

A CronJob is a Job that runs on a schedule, defined using cron syntax (e.g., `"0 2 * * *"` for daily at 2 AM). The CronJob controller creates a new Job object at each scheduled time. You can configure `concurrencyPolicy` to control overlap: `Forbid` (skip if previous is still running), `Replace` (kill previous and start new), or `Allow` (run concurrently). CronJobs also have `startingDeadlineSeconds` (how late a Job can start if it misses its window) and `successfulJobsHistoryLimit` / `failedJobsHistoryLimit` to control how many completed Jobs to keep.

> **AI Doctor Example:** Database migrations for AI Doctor's PostgreSQL are handled as a Kubernetes Job: `kubectl apply -f migration-job.yaml` creates a Pod that runs `alembic upgrade head`, and the Job completes when the migration finishes. If we needed nightly database backups, we'd use a CronJob running `pg_dump` at `"0 3 * * *"` (3 AM daily), writing the backup to a Cloud Storage bucket via `gsutil`.

### Q8. Explain the difference between a StatefulSet and a Deployment. When do you need a StatefulSet?

A Deployment treats all Pods as interchangeable. Pods get random names (e.g., `doctor-backend-7f8b9c-x4k2l`), are created and destroyed in any order, and share the same PersistentVolumeClaim (if any). When a Pod is recreated, it gets a new name and a new identity.

A StatefulSet provides guarantees that Deployments don't: **stable network identity** (Pods are named `postgres-0`, `postgres-1`, etc., and retain their names across restarts), **ordered deployment and scaling** (Pods are created in order 0→1→2 and terminated in reverse 2→1→0), and **stable persistent storage** (each Pod gets its own PersistentVolumeClaim via `volumeClaimTemplates`, and the PVC is retained even if the Pod is deleted and recreated).

You need a StatefulSet when your application requires one or more of these guarantees. The canonical example is databases: a PostgreSQL primary needs to be distinguishable from replicas, each instance needs its own dedicated storage that persists across restarts, and you can't start a replica before the primary is ready. Other examples include ZooKeeper, etcd, Kafka, Elasticsearch — distributed systems that have leader election, data replication, and identity-sensitive protocols.

You do not need a StatefulSet for stateless services, even if they use a shared PVC. If your Pods are interchangeable and don't need ordered startup or stable identity, use a Deployment. StatefulSets are more complex to manage — scaling down doesn't automatically delete PVCs (by design), updates roll through one Pod at a time, and you lose the speed of parallel rollouts. Use them only when the guarantees matter.

> **AI Doctor Example:** PostgreSQL runs as a StatefulSet `postgres` in the `doctor-app` namespace. The Pod `postgres-0` always mounts its own 10Gi PVC (`data-postgres-0`), so even if the Pod crashes and is rescheduled to a different node (in GKE Standard), it reattaches the same persistent disk. The `doctor-backend` and `doctor-frontend`, being stateless, run as Deployments.

---

## 2. Networking

### Q9. How does Kubernetes DNS work? How do pods discover services?

Every Kubernetes cluster runs a DNS server — typically CoreDNS, deployed as a Deployment in the `kube-system` namespace. When a Pod is created, Kubernetes configures its `/etc/resolv.conf` to point to the CoreDNS ClusterIP as the nameserver, and sets the search domains to include `<namespace>.svc.cluster.local`, `svc.cluster.local`, and `cluster.local`.

When a Pod makes a DNS query for a Service name — say `postgres` — the search domain expansion tries `postgres.doctor-app.svc.cluster.local` first (assuming the Pod is in the `doctor-app` namespace). CoreDNS looks up this name in its records (synced from the Kubernetes API server) and returns the Service's ClusterIP. The Pod can then connect to the ClusterIP, and kube-proxy handles routing to a backend Pod.

For Services of type ClusterIP, CoreDNS returns a single A record pointing to the virtual ClusterIP. For headless Services (no ClusterIP), CoreDNS returns A records for each individual Pod IP behind the Service. For ExternalName Services, CoreDNS returns a CNAME record pointing to the configured external hostname. SRV records are also available, which include port information — useful for discovering which port a Service is using.

The practical implication is that you can use short DNS names within the same namespace (`postgres`, `doctor-backend`) and fully qualified names across namespaces (`doctor-backend.doctor-app.svc.cluster.local`). This DNS-based discovery means you never hardcode Pod IPs — you reference Services by name, and Kubernetes DNS resolves them dynamically.

> **AI Doctor Example:** The `doctor-backend` FastAPI application connects to PostgreSQL using `DATABASE_URL=postgresql://user:pass@postgres:5432/doctor_db`. The name `postgres` resolves to the ClusterIP of the `postgres` Service in the same namespace. If we moved the database to a different namespace (say `databases`), the backend would need `postgres.databases.svc.cluster.local`.

### Q10. What is an Ingress and how does it differ from a LoadBalancer Service?

A LoadBalancer Service provisions an external cloud load balancer for a single Service. Each LoadBalancer Service gets its own external IP and its own cloud resource. If you have three Services (frontend, backend, admin), you'd get three load balancers, three external IPs, and three monthly bills.

An Ingress is a Kubernetes API object that defines HTTP(S) routing rules — host-based routing (e.g., `api.example.com` vs `app.example.com`) and path-based routing (e.g., `/api/*` goes to backend, `/*` goes to frontend). An Ingress does nothing by itself; it requires an **Ingress Controller** — a reverse proxy (NGINX, Traefik, HAProxy, or GKE's built-in GCLB controller) that reads Ingress resources and configures itself accordingly.

The key advantage is consolidation: a single Ingress controller (backed by a single load balancer) handles routing for all your Services. You also get features that LoadBalancer Services don't provide: TLS termination (attaching an SSL certificate), path rewriting, rate limiting, and header manipulation. This is significantly cheaper and more manageable in production.

In GKE, when you create an Ingress resource, the GKE Ingress controller automatically provisions a Google Cloud HTTP(S) Load Balancer with URL maps, backend services, health checks, and SSL certificates (via managed certificates). You don't need to install an NGINX Ingress controller — GKE handles it natively, though you can install one if you prefer NGINX's feature set.

> **AI Doctor Example:** The AI Doctor Ingress defines two rules: path `/api/*` routes to the `doctor-backend` ClusterIP Service on port 8000, and `/*` routes to the `doctor-frontend` ClusterIP Service on port 80. Both services use ClusterIP type (not LoadBalancer), and the Ingress controller is the only component with an external IP. A managed TLS certificate is attached to the Ingress for HTTPS.

### Q11. Explain the Kubernetes networking model. What are the three fundamental requirements?

The Kubernetes networking model is built on three fundamental requirements that every networking implementation must satisfy:

1. **Every Pod gets its own IP address.** Containers within a Pod share that IP (they differentiate via port numbers). No NAT is needed for Pod-to-Pod communication.

2. **All Pods can communicate with all other Pods without NAT.** A Pod on Node A can directly reach a Pod on Node B using the Pod's IP address. There is no network address translation between Pods — what a Pod sees as its own IP is the same IP that other Pods use to reach it.

3. **All Nodes can communicate with all Pods (and vice versa) without NAT.** Agents running on a node (like kubelet, kube-proxy) can reach any Pod in the cluster directly.

These requirements create a flat, routable network where every Pod can be treated as a virtual machine with its own IP. This simplifies application design because applications don't need to worry about port mapping or NAT traversal — they listen on their natural port and other Pods connect directly.

The Kubernetes project doesn't implement this networking itself — it delegates to **CNI (Container Network Interface) plugins**. Popular implementations include Calico (BGP-based routing + network policy enforcement), Cilium (eBPF-based, high-performance), Flannel (simple overlay network), and Weave Net. In GKE, Google uses its own VPC-native CNI that assigns Pod IPs from the VPC's secondary IP ranges, making Pods directly routable within the GCP VPC.

Understanding this model matters because it explains why Kubernetes networking feels different from Docker's port-mapping model. In Docker Compose, you publish ports (`-p 8000:8000`); in Kubernetes, Pods directly communicate on their assigned IPs and Services provide the discovery and load-balancing layer on top.

### Q12. What is a NetworkPolicy? Give an example of when you'd use one.

A NetworkPolicy is a Kubernetes resource that controls network traffic at the Pod level — which Pods can communicate with which other Pods, and on which ports. By default, Kubernetes allows all Pods to communicate with all other Pods (the flat networking model). NetworkPolicies let you restrict this by defining ingress (incoming) and egress (outgoing) rules.

NetworkPolicies use label selectors to identify which Pods the policy applies to (the `podSelector` field) and which Pods are allowed as traffic sources or destinations. You can also specify IP blocks (CIDR ranges) and ports. Policies are additive: if multiple policies select the same Pod, the union of their rules applies. Crucially, if any NetworkPolicy selects a Pod, all traffic not explicitly allowed by any policy is **denied**. An empty `podSelector: {}` in a policy selects all Pods in the namespace.

The practical nuance: NetworkPolicies require a CNI plugin that supports them. Flannel does not enforce NetworkPolicies; Calico, Cilium, and GKE's Dataplane V2 do. If your CNI doesn't support NetworkPolicies, the resources are accepted by the API server but have no effect — a dangerous silent failure. Always verify your CNI plugin supports enforcement.

> **AI Doctor Example:** A critical NetworkPolicy for AI Doctor would be: "Only `doctor-backend` Pods can reach the `postgres` Pod on port 5432. No other Pod in the cluster can connect to PostgreSQL." This prevents a compromised frontend Pod (or any other workload) from accessing the database directly. The policy would select Pods with `app: postgres` and only allow ingress from Pods with `app: doctor-backend` on TCP 5432.

### Q13. How does kube-proxy implement Services? What's the difference between iptables and IPVS mode?

kube-proxy runs on every node as a DaemonSet (or static Pod) and is responsible for implementing the Service abstraction. It watches the API server for Service and Endpoints objects and configures network rules on the node to redirect Service-bound traffic to the correct backend Pods.

In **iptables mode** (the default for most clusters), kube-proxy creates iptables rules — one chain per Service, with DNAT rules that probabilistically distribute traffic among backend Pods. For example, if a Service has 3 backends, kube-proxy creates rules with 1/3, 1/2, and 1/1 probability for each Pod. When a packet is destined for the Service's ClusterIP, it hits the iptables chain, gets DNAT'd to a randomly selected Pod IP, and is routed to that Pod. The downside is that iptables rules are processed linearly. In clusters with thousands of Services and Endpoints, the rule chains become very long, and connection setup latency increases.

In **IPVS mode**, kube-proxy uses Linux IPVS (IP Virtual Server), a kernel-level transport-layer load balancer built into the Linux netfilter framework. IPVS uses hash tables for lookup (O(1) instead of iptables' linear O(n)), supports multiple load-balancing algorithms (round-robin, least connections, weighted), and handles large numbers of Services much more efficiently. IPVS mode is recommended for large clusters (hundreds of Services or more).

A third mode, **nftables mode**, is newer (GA in Kubernetes 1.31) and replaces iptables with nftables rules, offering better performance than iptables while being simpler than IPVS. In GKE, Google uses its own dataplane (kube-proxy replacement with GKE Dataplane V2 / Cilium) that bypasses traditional kube-proxy entirely.

### Q14. What is a headless Service and when would you use one?

A headless Service is a Service with `.spec.clusterIP: None`. Unlike a regular Service, it doesn't get a virtual ClusterIP. Instead, DNS queries for the Service return the individual Pod IPs directly (as multiple A records), rather than a single ClusterIP. There's no kube-proxy load balancing — the client receives all Pod IPs and decides which one to connect to (or the DNS resolver may shuffle them).

Headless Services are essential for StatefulSets. When you create a headless Service for a StatefulSet, each Pod gets a predictable DNS name: `pod-name.service-name.namespace.svc.cluster.local`. For example, `postgres-0.postgres.doctor-app.svc.cluster.local` resolves directly to the IP of Pod `postgres-0`. This stable DNS identity persists across Pod restarts (as long as the StatefulSet re-creates the Pod with the same ordinal index).

Use headless Services when: (1) clients need to discover all individual Pods behind a Service (e.g., for client-side load balancing), (2) you need stable DNS names for individual StatefulSet Pods (required for database replication, leader election), or (3) you're using a service mesh that handles load balancing itself and doesn't need kube-proxy's ClusterIP.

> **AI Doctor Example:** The PostgreSQL StatefulSet uses a headless Service so that `postgres-0.postgres.doctor-app.svc.cluster.local` resolves to the specific Pod IP. If we later added a read replica (`postgres-1`), the backend could direct writes to `postgres-0.postgres` and reads to `postgres-1.postgres` by name, without needing to discover Pod IPs manually.

### Q15. How does pod-to-pod communication work across different nodes?

When two Pods on the same node communicate, the traffic stays local — packets travel through the virtual ethernet bridge on that node (typically `cbr0` or a CNI-managed bridge). Both Pods are connected to this bridge via virtual ethernet (veth) pairs, and the bridge routes traffic between them directly.

Cross-node Pod-to-Pod communication requires the CNI plugin to establish connectivity between nodes. There are two main approaches:

**Overlay networks** (used by Flannel/VXLAN, Calico in IPIP mode): The source node encapsulates the Pod-to-Pod packet inside another packet (e.g., VXLAN encapsulation) addressed to the destination node's IP. The destination node decapsulates the packet and delivers it to the target Pod. This works on any underlying network because the encapsulation uses the node network. The downside is overhead — extra headers, increased packet size, and CPU cost for encapsulation/decapsulation.

**Direct routing** (used by Calico in BGP mode, AWS VPC CNI, GKE VPC-native): Pod IPs are routable on the underlying network. The CNI configures routing tables (or uses BGP to advertise Pod CIDRs) so that the network infrastructure knows which node hosts which Pod IP range. Packets travel directly between nodes without encapsulation. This is more efficient but requires the underlying network to support it — either a cloud VPC that can handle additional routes, or routers that participate in BGP.

In GKE VPC-native mode, Pod IPs are assigned from secondary IP ranges of the VPC. Google's network fabric routes packets based on these IP ranges natively — no overlay, no encapsulation. This is one of the performance advantages of running on GKE.

### Q16. What is a Service mesh (e.g., Istio)? When would you need one?

A Service mesh is an infrastructure layer that manages service-to-service communication within a cluster. It works by injecting a sidecar proxy (typically Envoy) into every Pod. All traffic entering and leaving the Pod passes through this sidecar proxy, which gives the mesh control over every network call.

Service meshes provide several capabilities: **mTLS** (mutual TLS between all services — automatic encryption without application changes), **traffic management** (canary deployments, traffic splitting, retries, circuit breaking, fault injection), **observability** (detailed metrics, distributed tracing, access logs for every service-to-service call), and **policy enforcement** (authorization policies controlling which services can call which other services).

You need a service mesh when your microservice architecture is complex enough that these concerns become painful to implement at the application level. If you have 30 services and you need mTLS between all of them, implementing TLS in each service's code is impractical — a mesh does it transparently. If you need to gradually shift traffic from v1 to v2 of a service (1% → 10% → 50% → 100%), a mesh's traffic splitting does this without changing any application code.

You do NOT need a service mesh for small applications. If you have 3 services (like AI Doctor), the overhead of Istio (control plane resource consumption, sidecar memory per Pod, added latency per hop, operational complexity) isn't justified. Kubernetes Services and Ingress handle your needs. Consider a mesh when you have 10+ services, need mTLS everywhere, or need advanced traffic management. Lighter alternatives like Linkerd use less resources than Istio if you primarily need mTLS and observability without Istio's full feature set.

---

## 3. Storage

### Q17. What is the relationship between PersistentVolume, PersistentVolumeClaim, and StorageClass?

These three resources form Kubernetes' storage abstraction layer, separating the "how storage is provisioned" from the "what storage an application needs."

A **PersistentVolume (PV)** represents a piece of physical storage in the cluster — a GCE Persistent Disk, an AWS EBS volume, an NFS share, or a local SSD. It has a capacity, access modes, and a reclaim policy. PVs are cluster-level resources (not namespaced). They can be pre-provisioned by an administrator ("static provisioning") or created automatically by a provisioner ("dynamic provisioning").

A **PersistentVolumeClaim (PVC)** is a request for storage by a user. A PVC specifies the desired storage size, access mode, and optionally a StorageClass. PVCs are namespaced — they belong to the namespace where the Pod using them resides. When a PVC is created, the Kubernetes control plane tries to find a PV that matches the request (has enough capacity, the right access mode, and the same StorageClass). If a match is found, the PVC is "bound" to that PV. If no match exists and dynamic provisioning is configured, a new PV is created automatically.

A **StorageClass** defines the "type" of storage — the provisioner (which plugin creates the actual disk), the parameters (disk type, IOPS, replication), and the reclaim policy. Think of it as a blueprint: "when someone requests storage of class `fast-ssd`, use the GCE PD provisioner to create an SSD persistent disk in the same zone as the requesting node." StorageClasses enable dynamic provisioning — without them, an administrator would need to pre-create PVs for every anticipated PVC.

The flow is: Pod references a PVC → PVC requests storage from a StorageClass → StorageClass triggers the provisioner → Provisioner creates a PV (actual disk) → PVC binds to PV → Pod mounts the volume.

> **AI Doctor Example:** PostgreSQL's storage in AI Doctor works like this: The StatefulSet's `volumeClaimTemplates` creates a PVC named `data-postgres-0` requesting 10Gi from the `standard` StorageClass. GKE's default provisioner creates a 10Gi Persistent Disk in the same zone as the node running `postgres-0`, creates a PV representing that disk, and binds the PVC to it. The Pod mounts this PVC at `/var/lib/postgresql/data`.

### Q18. What are the different access modes for PersistentVolumes (RWO, ROX, RWX)?

Access modes define how a PersistentVolume can be mounted by nodes:

**ReadWriteOnce (RWO):** The volume can be mounted as read-write by Pods on a single node. Multiple Pods on the same node can read and write to it, but Pods on other nodes cannot mount it. This is the most common mode and the only mode supported by most block storage (GCE Persistent Disk, AWS EBS, Azure Disk).

**ReadOnlyMany (ROX):** The volume can be mounted as read-only by Pods on multiple nodes simultaneously. This is useful for sharing static content — for example, a pre-built asset bundle or a reference dataset that many Pods need to read but never modify.

**ReadWriteMany (RWX):** The volume can be mounted as read-write by Pods on multiple nodes simultaneously. This requires a shared filesystem like NFS, GlusterFS, CephFS, or managed solutions like GCP Filestore or AWS EFS. RWX is needed when multiple Pods on different nodes need to write to the same filesystem — for example, a shared upload directory or a shared cache.

There's also **ReadWriteOncePod (RWOP)**, added in Kubernetes 1.27 as stable: the volume can be mounted as read-write by a single Pod only (not just a single node). This is stricter than RWO and prevents even same-node Pods from accessing the volume, which is useful for sensitive data where you want to ensure exclusive access.

The key nuance: the access mode is a constraint, not an enforcement mechanism on all providers. It tells the scheduler what's allowed, and the storage provisioner decides whether it can actually support it. If you request RWX on GCE Persistent Disk (which doesn't support it), the PVC will remain unbound. Always check what access modes your storage backend supports.

### Q19. How does storage work differently in StatefulSets vs Deployments?

In a **Deployment**, you can attach a PVC in the Pod template, but all replicas share the same PVC. If you have a Deployment with 3 replicas and one PVC, all 3 Pods try to mount the same volume. With RWO storage (like GCE PD), this only works if all Pods land on the same node (since RWO allows multiple Pods on one node). If Pods get scheduled across nodes, all but one will fail to mount. To avoid this, you'd either use RWX storage (expensive, not always available) or set `replicas: 1`.

In a **StatefulSet**, you use `volumeClaimTemplates` instead of referencing a single PVC. The template acts as a blueprint — when the StatefulSet creates Pod `postgres-0`, it also creates PVC `data-postgres-0`. Pod `postgres-1` gets `data-postgres-1`, and so on. Each Pod gets its own dedicated PVC and PV. This is the fundamental difference: StatefulSets give each Pod its own persistent identity and storage.

Another critical difference: when a StatefulSet Pod is deleted (e.g., scaling down from 3 to 2), the PVC for `pod-2` is **not** deleted. It remains in the cluster, still bound to its PV. If you scale back up to 3, the new `pod-2` automatically re-attaches to the existing PVC `data-pod-2`, preserving its data. This is a safety mechanism — accidental scale-down doesn't destroy data. You have to manually delete orphaned PVCs if you want to reclaim storage.

In Deployment-world, if you delete and recreate the Deployment, the PVC remains (it's a separate object), and the new Deployment's Pods re-mount it. But you don't get per-replica PVCs — all replicas still share one.

### Q20. What happens to a PersistentVolume when its PVC is deleted? Explain reclaim policies.

When a PVC is deleted, the bound PV's behavior depends on its **reclaim policy**:

**Retain (default for manually provisioned PVs):** The PV is not deleted. It transitions to a "Released" state, meaning it's no longer bound to a PVC but its data is still there. A new PVC cannot automatically bind to a Released PV — an administrator must manually clean up the data and either delete the PV or make it available again by removing the `claimRef`. This is the safest option for production databases where accidental PVC deletion shouldn't destroy data.

**Delete (default for dynamically provisioned PVs):** The PV and its underlying storage resource (the actual cloud disk) are both deleted when the PVC is deleted. This is convenient for ephemeral workloads — storage is automatically cleaned up when no longer needed. However, it's dangerous for databases: deleting a PVC accidentally means your data is gone. For production StatefulSets, you should override the StorageClass's default reclaim policy to `Retain`.

**Recycle (deprecated):** The PV's data is scrubbed (basic `rm -rf /volume/*`) and the PV is made available again for new PVCs. This is deprecated in favor of dynamic provisioning and should not be used.

In practice, the reclaim policy is set on the StorageClass (applied to dynamically provisioned PVs) or directly on manually created PVs. You can change a PV's reclaim policy after creation with `kubectl patch pv <name> -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}'`. For any database PV, switching to Retain is a critical production safeguard.

> **AI Doctor Example:** The PostgreSQL PV for AI Doctor should use the `Retain` reclaim policy. If someone accidentally runs `kubectl delete pvc data-postgres-0`, the Retain policy ensures the underlying GCE Persistent Disk is preserved. An administrator can then create a new PVC that binds to the existing PV to recover the data, rather than losing the entire patient briefing database.

### Q21. What is ephemeral storage and how does it differ from persistent storage?

Ephemeral storage is storage that exists only for the lifetime of the Pod. When the Pod is deleted, restarted, or rescheduled, the data is gone. Kubernetes provides several forms of ephemeral storage:

**emptyDir:** A temporary directory created when a Pod starts and deleted when the Pod is removed. It starts empty, and all containers in the Pod can read and write to it (it's a good way to share files between sidecar containers). By default, `emptyDir` uses the node's filesystem, but you can set `medium: Memory` to use a tmpfs (RAM-backed filesystem) for faster I/O. The data in an `emptyDir` survives container restarts within the same Pod but not Pod deletion.

**Container filesystem:** The writable layer of the container (overlayfs). Data written to paths not backed by a volume lives here. This storage is lost when the container restarts, even within the same Pod — it's even more ephemeral than `emptyDir`.

**Generic ephemeral volumes:** Introduced in newer Kubernetes versions, these let you use a CSI driver to dynamically provision a volume that is deleted with the Pod. They're essentially short-lived PVCs that follow the Pod lifecycle.

Persistent storage (via PVCs) survives Pod deletion. The underlying disk exists independently of any Pod. This is essential for databases, file uploads, or any data that must survive restarts and rescheduling.

The practical consideration is **ephemeral storage limits**. Kubernetes tracks each Pod's ephemeral storage usage (container filesystem writes + `emptyDir` usage). You can set `resources.requests` and `resources.limits` for `ephemeral-storage`. If a Pod exceeds its ephemeral storage limit, it gets evicted. This prevents a runaway log file or temp file from filling up a node's disk. In GKE Autopilot, ephemeral storage is particularly constrained because nodes are shared and auto-managed.

### Q22. How would you back up persistent data in Kubernetes?

Backing up persistent data in Kubernetes involves multiple layers, depending on your requirements for consistency, frequency, and recovery granularity.

**Volume snapshots** are the most Kubernetes-native approach. The VolumeSnapshot API (GA since Kubernetes 1.20) lets you create point-in-time snapshots of PersistentVolumes through the CSI driver. You create a VolumeSnapshot object referencing a PVC, and the CSI driver triggers a snapshot of the underlying storage (e.g., a GCE PD snapshot). You can restore from a snapshot by creating a new PVC with a `dataSource` referencing the VolumeSnapshot. The caveat is consistency: a volume snapshot captures the disk at a point in time, but if the database has uncommitted writes in its WAL (Write-Ahead Log), the snapshot might be crash-consistent (like pulling the power plug) rather than application-consistent.

**Application-level backups** give you consistency. For PostgreSQL, this means `pg_dump` (logical backup) or `pg_basebackup` (physical backup). You'd run these as Kubernetes Jobs or CronJobs. `pg_dump` produces a consistent SQL dump even while the database is under load because PostgreSQL uses MVCC. The backup Job would mount a volume or stream directly to object storage (GCS, S3) using tools like `gsutil` or `aws s3 cp`.

**Third-party backup tools** like Velero (formerly Heptio Ark) provide cluster-wide backup and restore. Velero can back up both Kubernetes resources (YAML manifests) and PersistentVolume data. It integrates with cloud snapshot APIs and stores backups in object storage. Velero is especially useful for disaster recovery — you can restore an entire namespace (or entire cluster) from a Velero backup.

A robust backup strategy typically combines all three: volume snapshots for fast, infrastructure-level point-in-time recovery; application-level backups (pg_dump CronJob) for guaranteed-consistent logical backups; and Velero for cluster-wide disaster recovery.

> **AI Doctor Example:** For AI Doctor's PostgreSQL, a production backup strategy would include: (1) A CronJob running `pg_dump` nightly, streaming the output to a GCS bucket via `gsutil`. (2) GCE Persistent Disk snapshots via VolumeSnapshot every 6 hours for fast recovery. (3) Velero backing up the entire `doctor-app` namespace daily, storing both resource manifests and volume snapshots, enabling full namespace restore in a disaster recovery scenario.

---

## 4. Workloads & Scheduling

### Q23. Explain the rolling update strategy for Deployments. What are maxSurge and maxUnavailable?

When you update a Deployment's Pod template (typically by changing the container image), the Deployment controller performs a rolling update: it incrementally replaces old Pods with new ones, ensuring the application stays available throughout the transition. The Deployment creates a new ReplicaSet with the updated Pod template, scales it up, and scales the old ReplicaSet down.

Two parameters control the pace of the rollout:

**maxSurge** defines the maximum number of Pods that can exist above the desired replica count during the update. For example, with `replicas: 3` and `maxSurge: 1`, up to 4 Pods can exist at once (3 desired + 1 surge). This controls how fast new Pods come up. You can set it as an absolute number or a percentage (default: 25%, rounded up).

**maxUnavailable** defines the maximum number of Pods that can be unavailable during the update. With `replicas: 3` and `maxUnavailable: 1`, at least 2 Pods must always be running and ready. This controls how many old Pods are killed before new ones are ready. Default is also 25%, rounded down.

These two parameters work together to determine rollout behavior. Setting `maxSurge: 1, maxUnavailable: 0` means "always keep all desired replicas running, but allow one extra Pod during transition" — the safest but slowest option (the new Pod must be Ready before any old Pod is killed). Setting `maxSurge: 0, maxUnavailable: 1` means "never create extra Pods, but one Pod can be down during transition" — saves resources but reduces availability. The default `maxSurge: 25%, maxUnavailable: 25%` is a balanced middle ground.

The rolling update respects readiness probes. A new Pod isn't considered "available" until its readiness probe passes. If the readiness probe fails, the rollout stalls — the Deployment controller won't kill more old Pods and won't create more new Pods beyond maxSurge. This is your safety net: a broken new version is caught by the readiness probe, the rollout stalls, and you can roll back with `kubectl rollout undo`.

> **AI Doctor Example:** The `doctor-backend` Deployment uses `replicas: 2`, `maxSurge: 1`, `maxUnavailable: 0`. During an update: (1) A third Pod starts with the new image. (2) Kubernetes waits for the new Pod's readiness probe (`GET /health` on port 8000) to return 200. (3) Once ready, one old Pod is terminated. (4) A fourth Pod (second new one) starts. (5) Once ready, the last old Pod is terminated. Result: zero downtime, at most 3 Pods running during the transition.

### Q24. What are taints and tolerations? How do they differ from node affinity?

**Taints** are applied to nodes to repel Pods. A taint has a key, value, and effect. The three effects are: `NoSchedule` (new Pods without a matching toleration won't be scheduled here), `PreferNoSchedule` (the scheduler tries to avoid placing Pods here but will if necessary), and `NoExecute` (existing Pods without a matching toleration are evicted, and new ones aren't scheduled). Example: `kubectl taint nodes node1 gpu=true:NoSchedule` — only Pods that tolerate this taint will be scheduled on node1.

**Tolerations** are applied to Pods to allow them to schedule on tainted nodes. A toleration "matches" a taint if the key and value match and the effect matches. Having a toleration doesn't force the Pod onto the tainted node — it merely permits it. The Pod can still be scheduled on untainted nodes.

**Node affinity** is the opposite mechanism — it's applied to Pods to attract them to specific nodes (based on node labels). `requiredDuringSchedulingIgnoredDuringExecution` is a hard constraint (the Pod must land on a matching node or stays Pending). `preferredDuringSchedulingIgnoredDuringExecution` is a soft preference (the scheduler tries but doesn't guarantee it).

The key difference: taints and tolerations are about **repulsion** (keeping Pods off nodes unless they opt in), while node affinity is about **attraction** (pulling Pods toward specific nodes). In practice, you often use both together: taint GPU nodes so regular workloads don't land there, and add both a toleration AND a node affinity to your GPU workload so it (a) is allowed on GPU nodes and (b) prefers GPU nodes.

### Q25. What is pod affinity and anti-affinity? Give a practical example.

Pod affinity and anti-affinity control Pod placement relative to other Pods, not relative to nodes (that's node affinity). They use label selectors to reference other Pods and a `topologyKey` that specifies the domain of co-location (e.g., `kubernetes.io/hostname` for same-node, `topology.kubernetes.io/zone` for same-zone).

**Pod affinity** means "schedule this Pod on a node/zone where Pods matching this label selector are already running." For example, "schedule the cache Pod on the same node as the web server Pod" — this reduces network latency between them. The `requiredDuringSchedulingIgnoredDuringExecution` variant is a hard constraint; `preferredDuringSchedulingIgnoredDuringExecution` is soft.

**Pod anti-affinity** means "schedule this Pod on a node/zone where Pods matching this label selector are NOT running." The classic use case: "spread my 3 web server replicas across different nodes." With anti-affinity against `app: web-server` using `topologyKey: kubernetes.io/hostname`, the scheduler ensures no two web server Pods land on the same node. This provides high availability — a single node failure takes down at most one replica.

Practical example: AI Doctor has 2 backend replicas. We'd use pod anti-affinity with `topologyKey: kubernetes.io/hostname` to ensure `doctor-backend` replicas run on different nodes. If one node goes down, one replica survives. We'd use `preferredDuringSchedulingIgnoredDuringExecution` (soft) rather than `required` (hard) because in a small cluster, we might only have 2 nodes and don't want Pods stuck in Pending if both happen to be on the same node temporarily.

### Q26. How do resource requests and limits work? What happens when a pod exceeds its memory limit?

**Resource requests** tell the scheduler how much CPU and memory a Pod needs. The scheduler uses requests to decide which node has enough available capacity to host the Pod. If a node has 4 CPUs and existing Pods have total requests of 3.5 CPUs, only Pods requesting ≤ 0.5 CPU will be scheduled there. Requests are a guarantee — Kubernetes reserves that capacity for your Pod.

**Resource limits** cap the maximum resources a Pod can use. A Pod can burst above its CPU request up to its CPU limit (if the node has spare cycles), but cannot burst above its memory limit.

When a Pod **exceeds its memory limit**, the kernel's OOM killer terminates the container. Kubernetes reports this as `OOMKilled` in the Pod's status, and the kubelet restarts the container (according to the Pod's `restartPolicy`). If the container keeps OOMKilling, it enters `CrashLoopBackOff` — Kubernetes applies exponential backoff to restart attempts (10s, 20s, 40s, ... up to 5 minutes).

When a Pod **exceeds its CPU limit**, it's throttled — the kernel CFS scheduler limits the container's CPU time. The Pod runs slower but isn't killed. CPU throttling is often harder to diagnose than OOM because the Pod doesn't crash — it just gets slow. You can detect it via `container_cpu_cfs_throttled_seconds_total` in monitoring.

The relationship between requests and limits matters for QoS classes: **Guaranteed** (requests = limits for all containers), **Burstable** (requests < limits, or only some containers have limits), **BestEffort** (no requests or limits). Under memory pressure, Kubernetes evicts BestEffort Pods first, then Burstable, then Guaranteed.

> **AI Doctor Example:** The `doctor-backend` container might request `cpu: 250m, memory: 256Mi` and limit `cpu: 500m, memory: 512Mi`. Under normal load, it uses about 250m CPU and 200Mi memory. During a burst of AI briefing generation (calling Claude API), CPU usage spikes to 400m (allowed, under the 500m limit). If a memory leak in the application causes usage to hit 512Mi, the container is OOMKilled and restarted.

### Q27. What is a PodDisruptionBudget and why is it important?

A PodDisruptionBudget (PDB) defines the minimum number of Pods that must remain available during voluntary disruptions — node drains (maintenance, upgrades), cluster autoscaler scaling down, or `kubectl drain`. PDBs do not protect against involuntary disruptions like hardware failures or OOM kills.

You configure a PDB with either `minAvailable` (minimum Pods that must be running, as a number or percentage) or `maxUnavailable` (maximum Pods that can be down simultaneously). The PDB uses a label selector to identify which Pods it protects. During a voluntary disruption, Kubernetes checks the PDB before evicting a Pod. If evicting the Pod would violate the PDB, the eviction is blocked until another Pod comes up or a timeout is reached.

PDBs are important because without them, a node drain during a cluster upgrade can evict all your Pods simultaneously, causing downtime. Imagine you have a Deployment with 3 replicas across 3 nodes. A cluster upgrade drains nodes one at a time. Without a PDB, the drain might evict your Pod on node 1, and before it's rescheduled, start draining node 2 (evicting another Pod). Now you're down to 1 replica, potentially dropping requests. With a PDB of `minAvailable: 2`, Kubernetes won't drain node 2 until the evicted Pod from node 1 is rescheduled and running elsewhere.

PDBs are especially important on GKE, where node auto-upgrades happen automatically. Without PDBs, an auto-upgrade can take down your application's replicas faster than new ones can start. Always create PDBs for production workloads.

> **AI Doctor Example:** The `doctor-backend` PDB specifies `minAvailable: 1` (with 2 total replicas). During a GKE node upgrade, Kubernetes drains one node at a time. The PDB ensures that at least 1 backend Pod is always running and ready before the other node is drained. The `postgres` StatefulSet (1 replica) should also have a PDB, though with a single replica `minAvailable: 1` means the node drain will wait until the Pod is rescheduled — this adds delay to upgrades but prevents database downtime.

### Q28. How does the Kubernetes scheduler decide which node to place a pod on?

The Kubernetes scheduler (`kube-scheduler`) runs a two-phase process for every unscheduled Pod: **filtering** and **scoring**.

**Filtering (Predicates):** The scheduler eliminates nodes that cannot run the Pod. Filters include: (1) Does the node have enough CPU and memory to satisfy the Pod's resource requests? (2) Does the Pod have tolerations for the node's taints? (3) Does the Pod's `nodeSelector` or `nodeAffinity` match the node's labels? (4) Do port conflicts exist (the Pod needs host port 80, but another Pod already uses it)? (5) Do volume constraints permit it (e.g., a GCE PD can only attach to a node in the same zone)? (6) Do pod affinity/anti-affinity constraints allow it? After filtering, only "feasible" nodes remain.

**Scoring (Priorities):** The scheduler ranks the feasible nodes. Scoring functions include: `LeastRequestedPriority` (prefer nodes with more available resources), `BalancedResourceAllocation` (prefer nodes where CPU and memory usage are balanced), `InterPodAffinityPriority` (prefer nodes satisfying soft pod affinity), `NodeAffinityPriority` (prefer nodes matching soft node affinity), and `ImageLocalityPriority` (prefer nodes that already have the container image cached — reduces pull time). Each function returns a score from 0–100, weighted by configuration, and the scores are summed. The node with the highest total score wins.

If multiple nodes have the same highest score, the scheduler picks one randomly. If no nodes pass filtering, the Pod stays in `Pending` state, and the scheduler retries on its next cycle (typically every 100ms or when a relevant cluster event occurs).

In GKE Autopilot, the scheduler works differently — you don't see nodes. Autopilot provisions nodes automatically based on Pod requests. The scheduler is still there, but Google manages node provisioning to ensure Pods always have a place to run.

---

## 5. Configuration & Secrets

### Q29. What is the difference between a ConfigMap and a Secret? Are Secrets actually secure?

A **ConfigMap** stores non-sensitive configuration data as key-value pairs. Values can be short strings (environment variables) or entire files (configuration files). ConfigMaps are stored in etcd as plain text and can be consumed by Pods as environment variables, command-line arguments, or mounted files.

A **Secret** stores sensitive data (passwords, API keys, TLS certificates). Secrets are base64-encoded (not encrypted) in the API server and stored in etcd. They can be consumed the same way as ConfigMaps — environment variables or mounted files. When mounted as files, Kubernetes uses a tmpfs (in-memory filesystem) so the Secret data never hits the node's disk.

**Are Secrets actually secure?** The honest answer: **by default, not very.** Base64 is encoding, not encryption — anyone with `kubectl get secret -o yaml` access can decode the values. However, Kubernetes provides mechanisms to make Secrets genuinely secure: (1) **Encryption at rest** — you can configure the API server to encrypt Secrets in etcd using AES-CBC, AES-GCM, or a KMS provider (like GCP Cloud KMS). (2) **RBAC** — restrict who can read Secrets with fine-grained RBAC rules. (3) **Audit logging** — track who accessed which Secrets. (4) **Network policies** — prevent unauthorized Pods from accessing the API server.

In GKE, Secrets are encrypted at rest in etcd by default (Google manages the encryption key). You can enable **customer-managed encryption keys (CMEK)** via Cloud KMS for additional control. For even stronger secret management, use an external secret store (GCP Secret Manager, HashiCorp Vault) with the **External Secrets Operator** or **Secret Store CSI Driver**, which sync external secrets into Kubernetes Secrets.

> **AI Doctor Example:** AI Doctor uses a ConfigMap for `AI_MODEL: claude-sonnet-4-5-20250929`, `DEBUG: "false"`, `CORS_ORIGINS: "https://doctor-app.example.com"`. The Secret stores `ANTHROPIC_API_KEY` and `DATABASE_URL` (which contains the PostgreSQL password). In production on GKE, we'd enable application-layer Secret encryption with Cloud KMS and restrict Secret read access to only the `doctor-backend` ServiceAccount via RBAC.

### Q30. How can you inject environment variables into a pod from different sources?

Kubernetes provides several ways to set environment variables in a Pod's container:

**Static values** defined directly in the Pod spec:
```yaml
env:
  - name: APP_ENV
    value: "production"
```

**From a ConfigMap** — either a single key or all keys:
```yaml
env:
  - name: AI_MODEL
    valueFrom:
      configMapKeyRef:
        name: doctor-config
        key: AI_MODEL
# Or inject all keys as env vars:
envFrom:
  - configMapRef:
      name: doctor-config
```

**From a Secret** — same syntax, but with `secretKeyRef`:
```yaml
env:
  - name: ANTHROPIC_API_KEY
    valueFrom:
      secretKeyRef:
        name: doctor-secrets
        key: ANTHROPIC_API_KEY
```

**From the Pod's own fields** (Downward API):
```yaml
env:
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
  - name: POD_IP
    valueFrom:
      fieldRef:
        fieldPath: status.podIP
  - name: MEMORY_LIMIT
    valueFrom:
      resourceFieldRef:
        containerName: backend
        resource: limits.memory
```

There's also **mounted ConfigMaps/Secrets as files**, which aren't environment variables but serve a similar purpose. Mounting is preferred for large configurations (entire config files) and has the advantage that Kubernetes can update the mounted files when the ConfigMap/Secret changes (though the update has a delay and the Pod must be watching for file changes). Environment variables, in contrast, are set at Pod creation and do not update without a Pod restart.

### Q31. What is RBAC in Kubernetes? Explain Roles, ClusterRoles, RoleBindings, and ClusterRoleBindings.

RBAC (Role-Based Access Control) is Kubernetes' authorization system. It controls what actions a user or ServiceAccount can perform on which resources. RBAC is enabled by default on all modern clusters and is one of the most important security mechanisms.

A **Role** defines a set of permissions within a specific namespace. It specifies which API resources (Pods, Services, Secrets, etc.) can be accessed and which verbs (get, list, create, update, delete, watch) are allowed. For example, a Role might allow "get and list Pods in the doctor-app namespace."

A **ClusterRole** is like a Role but cluster-scoped — it can grant access to cluster-wide resources (Nodes, PersistentVolumes, Namespaces) or to resources across all namespaces. ClusterRoles can also be used within a namespace by binding them with a RoleBinding (this is a common pattern for reusable permission sets).

A **RoleBinding** connects a Role to a subject (User, Group, or ServiceAccount) within a namespace. "Grant the 'pod-reader' Role to ServiceAccount 'doctor-backend-sa' in namespace 'doctor-app'."

A **ClusterRoleBinding** connects a ClusterRole to a subject across the entire cluster. "Grant the 'cluster-admin' ClusterRole to user 'admin@company.com'."

The principle is: **Roles define what can be done. Bindings define who can do it.** The separation allows you to create reusable Roles and bind them to different subjects. The recommended practice is to follow the principle of least privilege — give each identity only the permissions it needs. In practice, avoid giving anyone `cluster-admin` except for genuine administrative use. For CI/CD pipelines, create a dedicated ServiceAccount with only the permissions needed (e.g., create/update Deployments in a specific namespace, but not delete namespaces or read Secrets).

### Q32. What is a ServiceAccount and how does it relate to RBAC?

A ServiceAccount is a Kubernetes identity for Pods (as opposed to Users, which represent humans). Every namespace has a `default` ServiceAccount, and every Pod runs as some ServiceAccount. The ServiceAccount determines what the Pod can do when it calls the Kubernetes API.

When a Pod is created, its ServiceAccount's token is automatically mounted inside the Pod at `/var/run/secrets/kubernetes.io/serviceaccount/token` (unless `automountServiceAccountToken: false` is set). This token is a JWT that the Pod presents when calling the API server. The API server authenticates the token and then applies RBAC rules based on the ServiceAccount's RoleBindings and ClusterRoleBindings.

The default ServiceAccount in each namespace has minimal permissions (essentially none, unless someone added bindings). In older Kubernetes versions (before 1.24), the default ServiceAccount had a long-lived Secret token auto-created. Since Kubernetes 1.24, bound service account tokens (short-lived, auto-rotated) are used instead, and long-lived tokens are no longer created by default.

The security best practice is: (1) Create a dedicated ServiceAccount for each workload instead of using the default. (2) Grant only the RBAC permissions that workload needs. (3) Set `automountServiceAccountToken: false` on Pods that don't need to call the Kubernetes API (most application Pods don't). This reduces the blast radius if a container is compromised — the attacker can't use the token to query the API server.

> **AI Doctor Example:** The `doctor-backend` Pod runs with a ServiceAccount `doctor-backend-sa` that has `automountServiceAccountToken: false` — the FastAPI app doesn't need to call the Kubernetes API. The `doctor-frontend` Pod similarly runs with its own ServiceAccount with no Kubernetes API access. Only the CI/CD pipeline's ServiceAccount has permission to create/update Deployments in the `doctor-app` namespace.

### Q33. How do you manage sensitive configuration (API keys, database passwords) in production K8s?

Managing secrets in production Kubernetes involves multiple layers. Using plain Kubernetes Secrets with RBAC is the baseline, but production environments need more:

**External secret stores** (GCP Secret Manager, AWS Secrets Manager, HashiCorp Vault) are the gold standard. Secrets live outside the cluster in a managed, audited, access-controlled vault. You integrate them with Kubernetes via: (1) **External Secrets Operator** — syncs external secrets into Kubernetes Secrets automatically. A CRD (`ExternalSecret`) defines which external secret to fetch and which Kubernetes Secret to create. (2) **Secrets Store CSI Driver** — mounts external secrets directly into Pods as files, without creating Kubernetes Secret objects at all (reducing the attack surface).

**Encryption at rest** is essential. Configure the API server (or use GKE's built-in feature) to encrypt Secrets in etcd using AES-256 or a KMS envelope. Without encryption at rest, anyone with access to the etcd data directory can read all Secrets in plain text.

**RBAC restrictions:** Create Roles that allow only specific ServiceAccounts to read specific Secrets. Don't give developers broad `get secrets` permissions in production namespaces. Use audit logs to track who accessed Secrets and when.

**GitOps considerations:** Never commit secrets to Git, even encrypted. Use **Sealed Secrets** (Bitnami) if you want to store encrypted secrets in Git — SealedSecret resources can only be decrypted by the controller running in the cluster. Alternatively, reference external secrets by name in your Git manifests and let the External Secrets Operator populate the actual values.

**Secret rotation:** External secret stores support automatic rotation. The External Secrets Operator can re-sync periodically, updating Kubernetes Secrets without manual intervention. For database passwords, this requires coordination with the application (connection pool refresh or Pod restart).

> **AI Doctor Example:** In production, AI Doctor would store `ANTHROPIC_API_KEY` and `DATABASE_URL` in GCP Secret Manager. An `ExternalSecret` resource in the `doctor-app` namespace references the GCP secrets and creates a Kubernetes Secret `doctor-secrets`. The External Secrets Operator runs with Workload Identity (no key files) to authenticate to GCP. The `doctor-backend` Pod mounts `doctor-secrets` as environment variables. Secret access is audited via GCP's audit logging and Kubernetes audit logs.

---

## 6. Scaling

### Q34. How does the Horizontal Pod Autoscaler (HPA) work? What metrics can it use?

The Horizontal Pod Autoscaler (HPA) automatically adjusts the number of Pod replicas in a Deployment, ReplicaSet, or StatefulSet based on observed metrics. It runs as a control loop (default every 15 seconds) that: (1) queries metrics, (2) calculates the desired replica count, (3) scales the target workload.

The core formula is: `desiredReplicas = ceil(currentReplicas × (currentMetricValue / desiredMetricValue))`. For example, if you have 2 replicas, current CPU utilization is 80%, and the target is 50%, the HPA calculates `ceil(2 × 80/50) = ceil(3.2) = 4` replicas. The HPA scales up to 4 replicas and re-evaluates on the next cycle.

**Metrics sources:**
- **Resource metrics** (CPU, memory utilization as a percentage of requests) — built-in, via metrics-server. Example: `targetAverageUtilization: 50` for CPU.
- **Custom metrics** — application-specific metrics exposed via the Custom Metrics API (e.g., using Prometheus Adapter). Example: scale based on request queue depth, active connections, or requests-per-second.
- **External metrics** — metrics from outside the cluster (e.g., Pub/Sub queue length, SQS depth). Example: scale up when the message queue has more than 1000 pending messages.

The HPA supports multiple metrics simultaneously — it calculates the desired replica count for each metric and uses the highest value. It also has behavior controls (`behavior.scaleUp` and `behavior.scaleDown`) for configuring stabilization windows and rate limits. The scale-down stabilization window (default 5 minutes) prevents flapping — the HPA won't scale down until the metric has been below the threshold for 5 consecutive minutes.

> **AI Doctor Example:** The `doctor-backend` HPA targets 60% CPU utilization with `minReplicas: 2` and `maxReplicas: 6`. During a clinic's morning rush when many patients check in and briefings are generated simultaneously, CPU usage spikes to 80%. The HPA scales from 2 to 3 replicas. If the load continues climbing, it scales further up to 6. After the rush subsides, the HPA waits 5 minutes (stabilization window) before scaling back down to 2.

### Q35. What is the Vertical Pod Autoscaler (VPA) and when would you use it instead of HPA?

The Vertical Pod Autoscaler (VPA) automatically adjusts the CPU and memory requests and limits of containers in a Pod. Instead of adding more Pods (horizontal scaling), VPA makes existing Pods bigger or smaller (vertical scaling).

VPA operates in three modes: **Off** (just recommends values, doesn't change Pods — useful for analysis), **Initial** (sets resource requests only when Pods are created, doesn't update running Pods), and **Auto** (evicts and recreates Pods with updated resource requests — the most disruptive but most automated mode).

VPA has three components: the **Recommender** (analyzes historical resource usage and produces recommendations), the **Updater** (evicts Pods that need resizing), and the **Admission Controller** (sets resource requests on new Pods during creation). The Recommender watches actual CPU and memory usage over time and suggests right-sized requests — critical for avoiding over-provisioning (wasting money) or under-provisioning (causing OOMs or throttling).

**When to use VPA over HPA:**
- For workloads that can't scale horizontally (e.g., a single-instance database, a legacy application that doesn't support multiple replicas)
- For batch jobs or worker processes where the resource profile varies (some tasks need 1Gi memory, others need 4Gi)
- For right-sizing initial resource requests — run VPA in "Off" mode to get recommendations without actually changing anything

**Important caveat:** You generally should not use VPA and HPA together on the same metric. If HPA scales based on CPU and VPA adjusts CPU requests, they can fight: VPA raises requests → HPA sees lower utilization percentage → HPA scales down → VPA lowers requests → loop. Since Kubernetes 1.27+, VPA in "Auto" mode can coexist with HPA if VPA is only adjusting memory and HPA scales on CPU or custom metrics.

### Q36. How does the Cluster Autoscaler work? How does it interact with HPA?

The Cluster Autoscaler automatically adjusts the number of nodes in the cluster based on Pod scheduling demands. It watches for two conditions:

**Scale up:** A Pod is in `Pending` state because no node has enough resources to schedule it (after filtering). The Cluster Autoscaler calculates which node pool's instance type would satisfy the Pod's requests, then adds a node to that pool. The new node registers with the cluster, and the scheduler places the pending Pod on it. Scale-up typically takes 1–3 minutes depending on the cloud provider.

**Scale down:** A node is underutilized (its Pods' requests total is below a threshold, default 50% of node capacity) for a sustained period (default 10 minutes). The Cluster Autoscaler checks if all Pods on that node can be rescheduled elsewhere, respects PDBs (won't drain if it would violate a PDB), and then drains and removes the node. Certain Pods prevent scale-down: Pods with local storage (emptyDir), Pods not managed by a controller, Pods with restrictive PDBs, and system Pods.

**HPA + Cluster Autoscaler interaction:** They work at different layers and complement each other. HPA increases Pod count → if there aren't enough nodes, Pods go Pending → Cluster Autoscaler adds nodes → Pods get scheduled. On the way down: HPA decreases Pod count → nodes become underutilized → Cluster Autoscaler removes nodes. The delay chain is: HPA reacts in 15–30 seconds, node provisioning takes 1–3 minutes. Total scale-up time from traffic spike to additional capacity is typically 1.5–4 minutes.

In GKE Autopilot, there is no separate Cluster Autoscaler — node provisioning is fully automatic and transparent. You just create Pods with resource requests, and GKE provisions the appropriate nodes. This eliminates the need to configure node pools, instance types, and autoscaler settings.

### Q37. What is the difference between scaling pods (HPA) and scaling nodes (Cluster Autoscaler)?

**HPA (Pod scaling)** operates at the application level. It changes the number of Pod replicas based on metrics (CPU, memory, custom metrics). It's a Kubernetes-native controller that talks to the Kubernetes API to adjust the `replicas` field of Deployments/StatefulSets. HPA is fast (15-second control loop) and doesn't require cloud provider integration. It assumes sufficient node capacity exists.

**Cluster Autoscaler (node scaling)** operates at the infrastructure level. It changes the number of virtual machines (nodes) in a node pool based on scheduling demand. It talks to the cloud provider's API (GCE, EC2, AKS) to add or remove instances. Cluster Autoscaler is slower (1–3 minutes for a new node) and requires cloud provider configuration.

They solve different problems: HPA answers "how many copies of my app should run?" while Cluster Autoscaler answers "how many machines do I need to run all requested copies?" You almost always use both together in production. Without Cluster Autoscaler, HPA can add replicas that stay Pending if nodes are full. Without HPA, Cluster Autoscaler never needs to add nodes (because no new Pods are requesting resources).

The important architectural insight: you should set **resource requests** accurately because they drive both systems. HPA uses requests to calculate utilization percentages, and Cluster Autoscaler uses requests to determine whether a node can fit a Pod. Inaccurate requests (too high = waste and premature scaling; too low = overloaded Pods and late scaling) undermine both autoscalers.

### Q38. How would you handle traffic spikes for a web application on Kubernetes?

Handling traffic spikes requires a multi-layered approach across application, Pod, and infrastructure levels:

**Layer 1: Pod-level autoscaling (HPA).** Configure HPA with aggressive scale-up and conservative scale-down. Use `behavior.scaleUp.stabilizationWindowSeconds: 0` (scale up immediately) and `behavior.scaleDown.stabilizationWindowSeconds: 300` (wait 5 minutes before scaling down to avoid flapping). Choose the right metric — CPU for compute-bound workloads, requests-per-second (custom metric) for I/O-bound workloads. Set a generous `maxReplicas` so the HPA has room to scale.

**Layer 2: Cluster-level autoscaling (Cluster Autoscaler).** Ensure the Cluster Autoscaler is enabled and configured to add nodes quickly. Use the `--scale-down-delay-after-add` flag to prevent premature scale-down of newly added nodes. Consider over-provisioning: run a low-priority "placeholder" Deployment with large resource requests. When real Pods need space, the placeholder Pods are evicted (they're low priority), and real Pods get scheduled immediately on the existing nodes — buying time while the Cluster Autoscaler provisions new nodes. This eliminates the 1–3 minute wait.

**Layer 3: Application-level resilience.** Use readiness probes so traffic isn't sent to Pods that aren't ready yet. Implement graceful shutdown (`preStop` hooks, `terminationGracePeriodSeconds`) so Pods finish in-flight requests before dying. Consider connection pooling, request queuing, or rate limiting at the application level.

**Layer 4: Ingress-level protection.** Configure rate limiting on the Ingress controller to prevent a single client from overwhelming the system. Use Cloud CDN or a WAF (Web Application Firewall) in front of the Ingress to absorb traffic and filter abuse.

**Layer 5: Proactive scaling.** If you know when spikes will happen (e.g., clinic opening hours), use a CronJob that patches the Deployment's `replicas` field or the HPA's `minReplicas` before the spike hits — pre-warming capacity.

> **AI Doctor Example:** During a clinic's check-in rush (8–9 AM), many patients load the React frontend and request AI briefings simultaneously. The `doctor-backend` HPA scales from 2 to 6 replicas based on CPU utilization. The Cluster Autoscaler adds a node to accommodate the additional Pods. A pre-warming CronJob runs at 7:45 AM, patching `minReplicas: 4` on the backend HPA. After 10 AM, the CronJob patches it back to `minReplicas: 2`, and the HPA gradually scales down.

---

## 7. GKE-Specific

### Q39. What are the key differences between GKE Autopilot and GKE Standard?

**GKE Standard** gives you full control over the node infrastructure. You choose machine types, configure node pools, manage node images, set autoscaling policies, and can SSH into nodes. You pay for the VMs whether or not Pods are running on them. You're responsible for node security patches, OS configuration, and right-sizing node pools.

**GKE Autopilot** is a fully managed mode where Google handles the node infrastructure entirely. You never see, configure, or manage nodes. You define your workloads (Pods with resource requests), and GKE provisions the appropriate compute. You pay per Pod resource request (CPU, memory, ephemeral storage), not per VM. Google manages security patching, node upgrades, OS hardening, and capacity planning.

Key differences:

| Aspect | Standard | Autopilot |
|--------|----------|-----------|
| Node management | You manage | Google manages |
| Pricing | Per VM (pay for idle capacity) | Per Pod resource request |
| SSH access to nodes | Yes | No |
| DaemonSets | Full support | Allowed but count toward billing |
| Privileged Pods | Allowed | Restricted |
| GPU support | Full control | Supported with specific configs |
| Node pools | Manual configuration | Automatic |
| Security posture | You harden | Google hardens (CIS benchmarks) |
| Resource efficiency | Your responsibility | Google optimizes bin-packing |

**When to choose Autopilot:** Small to medium workloads, teams without dedicated platform engineers, cost-conscious deployments (no idle VM waste), security-first environments (Google manages OS hardening). **When to choose Standard:** Need SSH access, need privileged containers (custom CNI, certain DaemonSets), need specific machine types (GPU configurations, high-memory instances), need fine-grained node control.

> **AI Doctor Example:** AI Doctor on GKE Autopilot is ideal for V1: a small team (no dedicated DevOps), 3 workloads (backend, frontend, PostgreSQL), no need for SSH or privileged containers. Autopilot's per-Pod pricing means we only pay for what the Pods request — no idle VMs. If we later add GPU-based local model inference (V2+), we might evaluate Standard for GPU node pool control, though Autopilot does support GPU Pods with specific machine families.

### Q40. What is Workload Identity and why is it better than using service account key files?

Workload Identity is GKE's recommended way to authenticate Pods to Google Cloud services (Cloud Storage, Secret Manager, BigQuery, etc.). It creates a mapping between a Kubernetes ServiceAccount and a Google Cloud IAM service account. When a Pod running as that Kubernetes ServiceAccount calls a GCP API, GKE automatically provides a short-lived, auto-rotated token for the mapped IAM service account.

**Without Workload Identity (the old way):** You create a GCP service account, download a JSON key file, store it as a Kubernetes Secret, and mount it in your Pod. The application uses the key file to authenticate. Problems: (1) The key file is a long-lived credential that doesn't expire. (2) It can be leaked (committed to Git, copied to a developer's machine). (3) Rotation requires manual coordination (generate new key, update Secret, restart Pods). (4) You have to distribute and manage Secret access.

**With Workload Identity:** No key files exist. Authentication happens through the GKE metadata server — the Pod requests a token, GKE validates the Kubernetes ServiceAccount, and issues a short-lived GCP token via the metadata server. Benefits: (1) No long-lived credentials to manage or leak. (2) Tokens are auto-rotated (typically 1-hour lifetime). (3) The mapping is controlled via IAM policy — revoke access centrally. (4) Follows the principle of least privilege — each Pod has its own IAM identity.

The setup involves: (1) Enable Workload Identity on the GKE cluster. (2) Create a GCP IAM service account with the needed permissions. (3) Create a Kubernetes ServiceAccount. (4) Add an IAM policy binding: `gcloud iam service-accounts add-iam-policy-binding gcp-sa@project.iam.gserviceaccount.com --member "serviceAccount:project.svc.id.goog[namespace/ksa-name]" --role roles/iam.workloadIdentityUser`. (5) Annotate the Kubernetes ServiceAccount with the GCP service account email. (6) Run Pods with that Kubernetes ServiceAccount.

> **AI Doctor Example:** The `doctor-backend` Pod needs to read from GCP Secret Manager (for `ANTHROPIC_API_KEY`). With Workload Identity: the Kubernetes ServiceAccount `doctor-backend-sa` is mapped to GCP IAM service account `doctor-backend@project.iam.gserviceaccount.com`, which has the `roles/secretmanager.secretAccessor` role. No key file is ever created or stored. If the External Secrets Operator also needs GCP access, it gets its own Kubernetes SA with its own IAM mapping — separate identities, separate permissions.

### Q41. How does GKE handle node upgrades? What is a surge upgrade?

GKE performs node upgrades when a new node image is available (security patches, Kubernetes minor version updates). In Standard mode, you can configure auto-upgrade policies or trigger upgrades manually. In Autopilot, Google handles upgrades automatically.

The default upgrade process works node by node: (1) GKE cordons a node (marks it unschedulable so no new Pods are placed there). (2) GKE drains the node — evicting Pods while respecting PodDisruptionBudgets. (3) The node is replaced with a new node running the updated image. (4) The scheduler places Pods on the new node. (5) GKE moves to the next node.

**Surge upgrade** improves the upgrade speed by provisioning additional nodes before draining old ones. You configure `maxSurge` (number of extra nodes created during upgrade) and `maxUnavailable` (number of nodes that can be unavailable simultaneously). With `maxSurge: 1, maxUnavailable: 0`, GKE creates one new node, waits for it to be ready, migrates Pods from one old node, deletes the old node, and repeats. This ensures capacity is never reduced during the upgrade. With `maxSurge: 3, maxUnavailable: 0`, GKE creates 3 new nodes at once, migrates faster — trading cloud cost (briefly running 3 extra nodes) for speed.

**Blue-green upgrade** (available in GKE) takes this further: GKE creates an entirely new node pool with the updated image, waits for all Pods to be rescheduled on the new pool, and then drains the old pool. This is the safest option — if the new version has issues, you can roll back by recreating Pods on the old pool. It's also the most expensive (briefly doubling node count).

Key considerations: always have PodDisruptionBudgets on production workloads to control how quickly Pods are evicted. Set maintenance windows to control when upgrades happen (e.g., only during off-peak hours). Use the `--release-channel` to control how aggressive updates are (Rapid, Regular, Stable).

### Q42. What is Binary Authorization in GKE?

Binary Authorization is a GKE security feature that enforces deploy-time policies on container images. It ensures that only trusted, verified container images can be deployed to your cluster. Think of it as a bouncer at the cluster entrance — images without the right credentials don't get in.

The system works with three components: **Attestations** (cryptographic signatures on container images, created by trusted parties), **Attestors** (entities who create attestations — typically your CI/CD pipeline), and **Policies** (rules defining which attestations are required for deployment).

The flow is: (1) Your CI/CD pipeline builds a container image and pushes it to Artifact Registry. (2) The pipeline performs checks — vulnerability scanning, code review verification, test passage — and creates an attestation (a cryptographic signature using a Cloud KMS key) on the image digest. (3) When someone (or the pipeline) tries to deploy the image to GKE, the Binary Authorization admission controller intercepts the request. (4) The controller checks whether the image has the required attestations. (5) If attestations are valid, the Pod is admitted. If not, the deployment is rejected.

Policies can be configured at different levels: require attestations from specific attestors (e.g., "must be signed by both the CI pipeline and the security team"), allow-list specific image registries or paths (e.g., "all images from gcr.io/my-project are allowed"), or run in dry-run mode (log violations but don't block — useful for rollout).

Binary Authorization prevents supply chain attacks (deploying a tampered image), unauthorized deployments (someone pushing an untested image directly), and ensures compliance (every production image has passed the required quality gates).

### Q43. How does GKE's VPC-native networking differ from routes-based networking?

**Routes-based networking** (the original GKE mode, now deprecated for new clusters) uses custom routes in the VPC routing table. Each node gets a `/24` Pod CIDR (256 IPs), and a VPC route is created for each node: "traffic for 10.4.0.0/24 → send to node X." This works but has limitations: VPC routes have a quota (by default 250 per VPC), so clusters are limited in size. Pods IPs are not natively routable from other VPC resources — they're only accessible via the node's IP through NAT.

**VPC-native networking** (alias IP mode) uses GCE alias IP ranges. Each node is assigned a secondary IP range for Pods and another for Services. Pod IPs come from the VPC's secondary CIDR ranges and are natively routable within the VPC — no encapsulation, no NAT. Other GCP resources (VMs, Cloud SQL with private IP, other GKE clusters with VPC peering) can communicate directly with Pod IPs.

Key advantages of VPC-native:
1. **Native routing:** Pod IPs are first-class citizens in the VPC. Cloud SQL, Memorystore, and other GCP services can reach Pod IPs directly.
2. **Scales better:** No per-node VPC route entries. Pod IP ranges are managed per node via alias IPs, which don't consume VPC route quota.
3. **Network Policy support:** VPC-native is required for GKE Dataplane V2 (Cilium-based), which enforces NetworkPolicies.
4. **Private Google Access:** Pods can access Google APIs (Cloud Storage, Secret Manager) via private IP without a NAT gateway.
5. **Required for Autopilot:** GKE Autopilot always uses VPC-native networking.

The trade-off is IP address planning: you need to allocate secondary IP ranges large enough for your expected Pods and Services. A `/14` secondary range gives ~250K Pod IPs, sufficient for most clusters. Plan this carefully because changing IP ranges requires recreating the cluster.

---

## 8. Real-World Scenarios

### Q44. Your deployment has 3 replicas but only 2 pods are running. How do you debug this?

Start by gathering information about the Deployment and its Pods:

```bash
kubectl get deployment doctor-backend -n doctor-app
kubectl get pods -l app=doctor-backend -n doctor-app
kubectl describe deployment doctor-backend -n doctor-app
```

The Deployment's events (from `kubectl describe`) will show if the ReplicaSet has trouble creating the third Pod. Common causes:

**Insufficient resources:** The third Pod is in `Pending` state because no node has enough CPU or memory to satisfy its resource requests. Check with `kubectl describe pod <pending-pod-name>` — look for events like "0/3 nodes are available: insufficient cpu." Fix: reduce resource requests, add nodes, or enable the Cluster Autoscaler.

**Pod is `Pending` due to PVC binding:** If the Pod uses a PVC that can't bind (wrong StorageClass, wrong zone), it stays Pending. The describe output will show "persistentvolumeclaim not found" or "volume binding failed."

**Pod is crashing (`CrashLoopBackOff`):** The third Pod starts but immediately fails. Check logs with `kubectl logs <pod-name> -n doctor-app --previous` (the `--previous` flag shows logs from the crashed container). Common causes: application error on startup (can't connect to database, missing env var), OOMKilled (memory limit too low), failing liveness probe (kills the container repeatedly).

**Image pull error (`ImagePullBackOff`):** The container image doesn't exist, the tag is wrong, or the node can't authenticate to the registry. Check events in `kubectl describe pod`. Fix: verify the image name and tag, check imagePullSecrets, verify the registry is accessible.

**Node affinity or anti-affinity preventing scheduling:** If pod anti-affinity requires different nodes and you only have 2 nodes, the third Pod can't be placed. Check the Pod's `nodeAffinity` and `podAntiAffinity` rules.

The systematic approach: (1) `kubectl get pods` — is the Pod Pending, CrashLoopBackOff, or ImagePullBackOff? (2) `kubectl describe pod <name>` — read the Events section. (3) `kubectl logs <name>` — check application logs. (4) Check the ReplicaSet with `kubectl describe rs <name>` for scaling events.

> **AI Doctor Example:** If the third `doctor-backend` Pod is Pending with "insufficient memory," it means the 2 running Pods plus the third's memory request exceed the node's allocatable memory. In GKE Autopilot, this shouldn't happen (Autopilot provisions nodes to fit), but in GKE Standard, you'd check if the Cluster Autoscaler is enabled and if the node pool has room to scale.

### Q45. A pod keeps getting OOMKilled. How do you diagnose and fix it?

OOMKilled means the container exceeded its memory limit and the Linux kernel's OOM killer terminated the process. Diagnosis and fix:

**Step 1: Confirm OOMKilled.** Check the Pod status and previous container status:
```bash
kubectl get pod <name> -n doctor-app -o jsonpath='{.status.containerStatuses[0].lastState}'
kubectl describe pod <name> -n doctor-app
```
Look for `reason: OOMKilled` and `exitCode: 137` (128 + 9 = SIGKILL).

**Step 2: Check current memory limits.** Compare the container's memory limit with its actual usage:
```bash
kubectl top pod <name> -n doctor-app
kubectl get pod <name> -o jsonpath='{.spec.containers[0].resources.limits.memory}'
```
If the limit is 256Mi and the Pod was using 255Mi before being killed, the limit is too tight.

**Step 3: Analyze the application.** Is this a genuine memory leak, or does the application legitimately need more memory? Check application-level metrics (heap size, connection pool, cache size). For Java apps, review JVM heap settings. For Python apps, check if large objects are accumulating in memory (use memory profilers like `tracemalloc`).

**Step 4: Fix.** If the application legitimately needs more memory (e.g., it processes large patient records in memory), increase the memory limit. If it's a memory leak, fix the leak — don't just raise the limit, or it will OOM again at the higher limit. A common pattern: set `requests` to what the app normally uses and `limits` to 1.5–2x that, giving headroom for spikes without allowing unbounded growth.

**Step 5: Prevent recurrence.** Set up monitoring alerts when a container's memory usage exceeds 80% of its limit — this gives you warning before OOMKill. Consider using VPA in recommendation mode to right-size your requests and limits based on actual usage data.

> **AI Doctor Example:** If `doctor-backend` is OOMKilled with a 512Mi limit, it might be because generating AI briefings loads the full patient record into memory. If patient records average 2Mi but some outliers are 50Mi, the memory spike during briefing generation could push usage over the limit. Fix: either increase the limit to 768Mi to handle outliers, or implement streaming/chunking in the briefing service to process large records without loading everything into memory at once.

### Q46. A namespace is stuck in "Terminating" state. What's happening and how do you fix it?

When you delete a namespace with `kubectl delete namespace <name>`, Kubernetes needs to delete all resources within it first — Pods, Services, ConfigMaps, Secrets, PVCs, Deployments, CRDs, etc. The namespace stays in `Terminating` state until all resources are cleaned up. If a resource can't be deleted, the namespace gets stuck.

**Common causes:**

1. **Stuck finalizers:** Resources (especially CRDs from operators) may have finalizers — keys in `metadata.finalizers` that tell Kubernetes "don't delete this resource until I've done cleanup." If the controller responsible for removing the finalizer is gone (e.g., you uninstalled an operator before deleting its CRDs), the finalizer never gets removed, and the resource (and namespace) are stuck.

2. **API resources unavailable:** If a CRD was deleted before its instances were deleted, the API server can't list/delete the instances because the CRD (which defines the API endpoint) is gone. The namespace controller can't verify all resources are deleted, so the namespace stays Terminating.

3. **Pods stuck in termination:** A Pod might not respond to SIGTERM and the `terminationGracePeriodSeconds` hasn't elapsed yet. This is temporary and resolves when the grace period ends and SIGKILL is sent.

**Diagnosis:**
```bash
kubectl get namespace <name> -o yaml
# Check .status.conditions for what's blocking
kubectl api-resources --verbs=list --namespaced -o name | xargs -n 1 kubectl get --show-kind --ignore-not-found -n <name>
```

**Fix for stuck finalizers:** Remove the finalizer from the stuck resource:
```bash
kubectl get <resource-type> -n <name> -o yaml
# Edit to remove the finalizer
kubectl patch <resource> -n <name> --type merge -p '{"metadata":{"finalizers":[]}}'
```

**Nuclear option (last resort):** Force-remove the namespace by patching its finalizer via the API server directly:
```bash
kubectl get namespace <name> -o json | jq '.spec.finalizers = []' | kubectl replace --raw "/api/v1/namespaces/<name>/finalize" -f -
```

This bypasses normal cleanup and may leave orphaned cloud resources (load balancers, disks). Use only when you've verified that underlying resources are cleaned up or don't exist.

### Q47. You need to run a database migration before deploying a new version of your app. How do you do this in K8s?

Database migrations in Kubernetes require careful ordering: the migration must complete before the new application version starts (because the new code expects the new schema). There are several approaches:

**Approach 1: Kubernetes Job (recommended for most cases).** Create a Job that runs the migration command (`alembic upgrade head` for Python, `npx prisma migrate deploy` for Node). Run the Job before updating the Deployment. In a CI/CD pipeline:
```bash
kubectl apply -f migration-job.yaml
kubectl wait --for=condition=complete job/migration --timeout=300s
kubectl apply -f deployment.yaml
```
The `kubectl wait` blocks until the Job succeeds. If the migration fails, the pipeline stops, and the old Deployment continues running the old version. This is simple and reliable.

**Approach 2: Init container.** Add an init container to the Deployment's Pod template that runs the migration. Init containers run before the main containers start. This ensures every Pod runs the migration before starting the application. However, this has a problem with multiple replicas: if you have 3 replicas, all 3 init containers run the migration concurrently. Alembic and most migration tools handle this safely (they use database locks), but it's wasteful and can cause lock contention. To mitigate, you can use a migration-specific lock or only run init containers on one Pod (but Kubernetes doesn't natively support this).

**Approach 3: Helm hooks or Kustomize generators.** Helm supports `pre-upgrade` hooks that run Jobs before updating resources. Kustomize doesn't have native hooks, but you can achieve ordering through your CI/CD pipeline (apply the Job, wait, apply the rest).

**Key considerations:** (1) Migrations should be backwards-compatible — the old version of the app should work with the new schema, in case the rollout takes time or fails mid-way. (2) Use migration versioning (Alembic's version table, Prisma's migration history) to ensure idempotency. (3) Set a `backoffLimit` on the Job so failed migrations don't retry indefinitely. (4) Consider a separate `migration` Deployment that runs once rather than an init container that runs on every Pod restart.

> **AI Doctor Example:** Before deploying a new `doctor-backend` version that adds a `priority_score` column to the flags table, the CI/CD pipeline runs: (1) `kubectl apply -f migration-job.yaml` — a Job that runs `alembic upgrade head` using the `DATABASE_URL` from the `doctor-secrets` Secret. (2) `kubectl wait --for=condition=complete job/add-priority-score-migration --timeout=120s`. (3) On success, `kubectl apply -f doctor-backend-deployment.yaml` with the new image. The Alembic migration is written to be backwards-compatible (adds a nullable column), so existing backend Pods continue working during the rollout.

### Q48. How would you implement zero-downtime deployments?

Zero-downtime deployment means users experience no errors or service interruptions during the deployment process. It requires coordination across multiple layers:

**1. Rolling update strategy.** Use `maxSurge: 1, maxUnavailable: 0` in the Deployment's strategy. This ensures the old Pods are not killed until new Pods are ready. At no point is the replica count below the desired count.

**2. Readiness probes.** Define a readiness probe that verifies the new Pod can actually serve traffic (not just that the process started). For a web application, the probe should check the HTTP endpoint (`httpGet: path: /health, port: 8000`). The Pod only receives traffic from the Service after its readiness probe passes. Without a readiness probe, Kubernetes might route traffic to a Pod that's still initializing, causing errors.

**3. Graceful shutdown.** When an old Pod is terminated, it receives SIGTERM. The application should: (a) stop accepting new connections, (b) finish processing in-flight requests, and (c) exit cleanly. Set `terminationGracePeriodSeconds` (default 30s) to give the application enough time to drain. Use a `preStop` hook with a small sleep (`sleep 5`) to give kube-proxy time to remove the Pod from the Service's endpoints before the application starts shutting down — this prevents the race condition where a Pod is removed from the Service but still receives new requests briefly.

**4. PodDisruptionBudget.** Ensure `minAvailable` is set so that node drains (during upgrades) don't take down all replicas simultaneously.

**5. Connection draining on the load balancer.** Ingress controllers (NGINX, GCE) support connection draining — when a backend is removed, existing connections are allowed to complete before the backend is fully deregistered. Configure an appropriate draining timeout.

**6. Backwards-compatible database migrations.** As discussed in Q47, migrations should not break the old version of the application. Schema changes should be additive (add columns, not rename or remove them in the same deployment).

The full sequence for zero-downtime: New Pod starts → passes readiness probe → added to Service endpoints → starts receiving traffic → old Pod receives SIGTERM → old Pod is removed from Service endpoints → old Pod finishes in-flight requests → old Pod exits. Users are routed to the new or old Pod seamlessly throughout.

> **AI Doctor Example:** For the `doctor-backend` zero-downtime deployment: (1) Deployment uses `maxSurge: 1, maxUnavailable: 0`. (2) Readiness probe: `httpGet /health port 8000 initialDelaySeconds: 5 periodSeconds: 10`. (3) `preStop` hook: `exec: command: ["sleep", "5"]` — gives kube-proxy 5 seconds to update iptables before the FastAPI server starts shutting down. (4) FastAPI's Uvicorn server handles SIGTERM gracefully by default (finishes in-flight requests). (5) `terminationGracePeriodSeconds: 30` — enough time for the longest API call (AI briefing generation, which may take up to 15 seconds due to the Claude API call).

---

## 9. Security

### Q49. What is a SecurityContext and what can it control?

A SecurityContext defines privilege and access control settings for a Pod or individual container. It's set in the Pod spec under `spec.securityContext` (Pod-level, applies to all containers) or `spec.containers[].securityContext` (container-level, overrides Pod-level for that container).

Key settings at the **container level:**
- `runAsUser: 1000` — run the container process as UID 1000 (not root)
- `runAsNonRoot: true` — fail to start if the container image tries to run as root
- `readOnlyRootFilesystem: true` — make the container's root filesystem read-only (writes only to mounted volumes)
- `allowPrivilegeEscalation: false` — prevent child processes from gaining more privileges than the parent (blocks `setuid` binaries)
- `capabilities.drop: ["ALL"]` — drop all Linux capabilities (a fine-grained alternative to full root access)
- `capabilities.add: ["NET_BIND_SERVICE"]` — selectively add back specific capabilities if needed

Key settings at the **Pod level:**
- `runAsUser`, `runAsGroup` — default UID/GID for all containers
- `fsGroup` — sets the group ownership of mounted volumes, so the non-root user can write to them
- `seccompProfile: { type: RuntimeDefault }` — apply the container runtime's default seccomp profile, which blocks dangerous syscalls

SecurityContexts are the primary mechanism for implementing the principle of least privilege at the container level. A properly configured SecurityContext ensures that even if an attacker exploits a vulnerability in your application, they can't escalate to root, can't write to the filesystem (making persistence harder), and can't use dangerous kernel capabilities.

> **AI Doctor Example:** The `doctor-backend` container's SecurityContext: `runAsNonRoot: true`, `runAsUser: 1000`, `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`, `capabilities: { drop: ["ALL"] }`. The FastAPI application runs as a non-root user, can't modify its own filesystem (only writes to the mounted tmp volume for Uvicorn's temporary files), and has no Linux capabilities. If an attacker gained code execution through a vulnerability, they'd be a non-root user in a read-only filesystem with no capabilities — severely limiting what they can do.

### Q50. Explain Pod Security Standards (Privileged, Baseline, Restricted).

Pod Security Standards (PSS) are three predefined security profiles that define what a Pod is allowed to do. They replaced the older PodSecurityPolicy (PSP), which was removed in Kubernetes 1.25. PSS is enforced via the built-in **Pod Security Admission** controller, which is enabled by default since Kubernetes 1.25.

**Privileged:** No restrictions at all. Pods can run as root, use host networking, mount any volume, and use all Linux capabilities. This is for system-level infrastructure like CNI plugins, logging agents, and storage drivers that genuinely need host access. Never use this for application workloads.

**Baseline:** Prevents known privilege escalation vectors while remaining broadly compatible with common workloads. Restrictions include: no `hostNetwork`, `hostPID`, or `hostIPC`; no `privileged` containers; restricted `capabilities` (only a limited set allowed); no `hostPath` volumes. Most applications run fine under Baseline without modification.

**Restricted:** The most hardened profile. In addition to Baseline restrictions: containers must run as non-root (`runAsNonRoot: true`), must drop all capabilities, must use a seccomp profile, and must have `allowPrivilegeEscalation: false`. This is the target for production application workloads. It requires that your container images are built to run as non-root.

You apply PSS to namespaces via labels:
```yaml
metadata:
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
```

The three modes: `enforce` (block non-compliant Pods), `audit` (allow but log violations), `warn` (allow but show warnings to the user). A common rollout strategy: start with `warn: restricted` to see which Pods would fail, fix them, then switch to `enforce: restricted`.

> **AI Doctor Example:** The `doctor-app` namespace uses `enforce: restricted`. All AI Doctor Pods (backend, frontend, PostgreSQL) are configured with non-root users, dropped capabilities, seccomp profiles, and read-only root filesystems. When a developer accidentally deploys a Pod without `runAsNonRoot: true`, the admission controller rejects it immediately with a clear error message explaining the violation.

### Q51. How do you scan container images for vulnerabilities in a CI/CD pipeline?

Container image scanning inspects the layers of a container image for known vulnerabilities (CVEs) in installed packages, OS libraries, and application dependencies. It's a critical step in the CI/CD pipeline — catching vulnerabilities before they reach production.

**Scanning tools:**
- **Trivy** (Aqua Security, open source): Scans container images, filesystems, Git repos, and Kubernetes manifests. Fast, offline-capable, and widely used. `trivy image my-app:latest --severity HIGH,CRITICAL`
- **Grype** (Anchore, open source): Focused on vulnerability scanning for container images and SBOMs. `grype my-app:latest`
- **GCP Artifact Analysis** (formerly Container Analysis): Integrated with Artifact Registry, automatically scans images when pushed. Results are available via the GCP Console and API.
- **Snyk Container**: Commercial tool with deep dependency analysis and fix recommendations.

**CI/CD integration pattern:**
1. Build the container image in the CI pipeline.
2. Run the scanner against the image before pushing to the registry.
3. Fail the pipeline if HIGH or CRITICAL vulnerabilities are found (configurable threshold).
4. Push the image to the registry only if the scan passes.
5. Optionally, create a Binary Authorization attestation (on GKE) to prove the image was scanned.

**Best practices:**
- Use minimal base images (`distroless`, `alpine`, `slim` variants) to reduce the attack surface — fewer packages means fewer potential vulnerabilities.
- Pin base image versions (`python:3.12-slim@sha256:abc123`) instead of using `latest` tags — ensures reproducibility and prevents unexpected vulnerability introduction.
- Scan regularly, not just at build time — new CVEs are published daily. GCP Artifact Analysis provides continuous scanning of stored images.
- Distinguish between fixable and unfixable vulnerabilities. A CRITICAL CVE with no available fix might require switching to a different base image or accepting the risk with a documented exception.

### Q52. What is the principle of least privilege and how do you apply it in Kubernetes?

The principle of least privilege states that every component should have only the minimum permissions necessary to perform its function — nothing more. In Kubernetes, this applies across multiple dimensions:

**Pod/Container level:** Run containers as non-root users (`runAsNonRoot: true`). Drop all Linux capabilities and add back only what's needed. Use `readOnlyRootFilesystem: true`. Set `allowPrivilegeEscalation: false`. Use the `restricted` Pod Security Standard. Each of these limits what a compromised container can do.

**RBAC level:** Create dedicated ServiceAccounts per workload (don't use `default`). Grant Roles with only the verbs and resources needed. Prefer namespaced Roles over ClusterRoles. Avoid wildcard permissions (`*` verbs or `*` resources). Review and audit RoleBindings regularly. Example: a CI/CD ServiceAccount needs `create` and `update` on Deployments in one namespace — not `*` on `*` in all namespaces.

**Network level:** Use NetworkPolicies to restrict which Pods can communicate. Default-deny all ingress and egress, then explicitly allow required paths. PostgreSQL should only accept connections from the backend Pod, not from the entire namespace.

**Secret level:** Restrict Secret read access to only the ServiceAccounts that need them. Don't mount Kubernetes API tokens into Pods that don't need them (`automountServiceAccountToken: false`). Use external secret managers for additional audit trails.

**Image level:** Use minimal base images (fewer installed packages = smaller attack surface). Don't install debugging tools (curl, wget, netcat) in production images — they're useful for attackers. Use multi-stage builds to ensure build tools don't end up in the final image.

**Cloud IAM level:** (GKE-specific) Use Workload Identity with separate GCP service accounts per workload. Each service account has only the IAM roles it needs. The backend needs `secretmanager.secretAccessor` — it doesn't need `storage.admin`.

The cumulative effect: even if an attacker exploits a vulnerability in one component, the blast radius is contained. They can't escalate privileges, can't move laterally to other services, can't read secrets they shouldn't have access to, and can't communicate with services outside the allowed network paths.

### Q53. How do you prevent containers from running as root?

Preventing containers from running as root requires action at both the container image level and the Kubernetes configuration level:

**In the Dockerfile:**
```dockerfile
FROM python:3.12-slim
# Create a non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser appuser
# Set ownership of app files
COPY --chown=appuser:appuser . /app
WORKDIR /app
# Switch to non-root user
USER appuser
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

The `USER` directive changes the default user for subsequent commands and for runtime. This is the first line of defense — the container starts as a non-root user by default.

**In the Kubernetes Pod spec:**
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  runAsGroup: 1000
  fsGroup: 1000
```

`runAsNonRoot: true` is a Kubernetes-level enforcement — even if the container image specifies `USER root`, Kubernetes will refuse to start the container. This catches misconfigured images. `runAsUser: 1000` explicitly sets the UID, overriding whatever the image specifies.

**At the namespace level (Pod Security Admission):**
```yaml
metadata:
  labels:
    pod-security.kubernetes.io/enforce: restricted
```

The `restricted` standard requires `runAsNonRoot: true` for all Pods in the namespace. Any Pod submitted without this setting is rejected by the admission controller, preventing accidental deployments of root-running containers.

**Common issues when running as non-root:**
- File permissions: The non-root user needs read access to application files and write access to temp directories. Use `COPY --chown` in the Dockerfile and `fsGroup` in the Pod spec for volume permissions.
- Port binding: Non-root users can't bind to ports below 1024. Use ports like 8000, 8080, or 3000 instead of 80 or 443. The Ingress/Service layer handles external port mapping.
- Package installation: Some images try to install packages at startup. Move all `apt-get install` commands before the `USER` directive in the Dockerfile.

> **AI Doctor Example:** The `doctor-backend` image uses `USER appuser` (UID 1000) in its Dockerfile. The Pod spec sets `runAsNonRoot: true` and `runAsUser: 1000`. The FastAPI server binds to port 8000 (not 80). The `doctor-frontend` NGINX image is configured to run as non-root by using the `nginx-unprivileged` base image, which listens on port 8080 instead of 80.

---

## 10. Debugging & Troubleshooting

### Q54. A pod is in CrashLoopBackOff. Walk through your debugging process.

CrashLoopBackOff means the container starts, crashes, is restarted by kubelet, crashes again, and Kubernetes applies exponential backoff to restarts (10s → 20s → 40s → 80s → ... → 300s max). This is one of the most common issues you'll encounter.

**Step 1: Check Pod status and events.**
```bash
kubectl get pod <name> -n doctor-app
kubectl describe pod <name> -n doctor-app
```
The Events section often reveals the cause immediately. Look for: OOMKilled (exit code 137), failed liveness probe, image pull errors, or volume mount failures. The `containerStatuses[].lastState.terminated.reason` field tells you why the container stopped.

**Step 2: Check container logs.**
```bash
kubectl logs <name> -n doctor-app           # Current container's logs (may be empty if it crashed immediately)
kubectl logs <name> -n doctor-app --previous  # Previous container's logs (this is the key command)
```
`--previous` shows logs from the last crashed container instance. This is where you'll see the application error — a missing environment variable, a database connection failure, a Python traceback, etc.

**Step 3: Check the exit code.**
Exit code 1 = application error (unhandled exception). Exit code 137 = OOMKilled (or SIGKILL). Exit code 139 = segfault. Exit code 143 = SIGTERM (graceful shutdown). These hint at the category of problem.

**Step 4: Debug interactively (if the container starts but crashes quickly).**
```bash
# Override the command to just sleep, so you can exec into it
kubectl run debug-pod --image=<same-image> --command -- sleep 3600
kubectl exec -it debug-pod -n doctor-app -- /bin/sh
# Now manually run the application command and observe the error
```

**Step 5: Check resource limits.** If the container is OOMKilled, increase memory limits. If it's CPU-throttled and timing out on startup (causing liveness probe failure), increase CPU limits or adjust the `initialDelaySeconds` on the liveness probe.

**Step 6: Check liveness probe configuration.** A misconfigured liveness probe (wrong path, wrong port, `initialDelaySeconds` too short) causes Kubernetes to kill a healthy container that hasn't finished starting yet. This looks like CrashLoopBackOff but the root cause is the probe, not the application.

> **AI Doctor Example:** The `doctor-backend` Pod enters CrashLoopBackOff. `kubectl logs --previous` shows `sqlalchemy.exc.OperationalError: could not connect to server: Connection refused`. The Pod can't reach PostgreSQL — either the `postgres` Pod is down, the `DATABASE_URL` Secret has the wrong host/port, or a NetworkPolicy is blocking the connection. Check: (1) `kubectl get pod -l app=postgres -n doctor-app` — is PostgreSQL running? (2) `kubectl get secret doctor-secrets -o yaml` — is `DATABASE_URL` correct? (3) `kubectl get networkpolicy -n doctor-app` — is backend→postgres traffic allowed?

### Q55. A pod is stuck in Pending state. What could be wrong?

A Pod in `Pending` state has been accepted by the API server but hasn't been scheduled to a node. The scheduler couldn't find a suitable node, or the Pod is waiting for a prerequisite.

**Diagnosis:**
```bash
kubectl describe pod <name> -n doctor-app
```
The Events section is the single most important diagnostic. It will tell you exactly why.

**Common causes:**

1. **Insufficient resources.** "0/3 nodes are available: 1 Insufficient cpu, 2 Insufficient memory." The Pod's resource requests exceed what any node can offer. Fix: reduce requests, add nodes, or enable the Cluster Autoscaler.

2. **No matching nodes for nodeSelector/affinity.** "0/3 nodes are available: 3 node(s) didn't match node selector." The Pod requires a node with a specific label (e.g., `gpu: true`) and no such node exists. Fix: add the label to a node or adjust the selector.

3. **Taints with no matching toleration.** "0/3 nodes are available: 3 node(s) had taints that the pod didn't tolerate." All nodes are tainted and the Pod doesn't have the required toleration. Fix: add a toleration to the Pod spec or remove the taint from a node.

4. **PVC not bound.** "persistentvolumeclaim 'data-postgres-0' not found" or "waiting for first consumer." The Pod references a PVC that either doesn't exist or can't be provisioned (wrong StorageClass, no available PVs, zone mismatch). Fix: check the PVC status with `kubectl get pvc -n doctor-app`.

5. **Too many Pods.** In GKE Standard, each node has a maximum Pod count (default 110). If all nodes are at capacity (by count, not by resources), new Pods can't be scheduled.

6. **Pod anti-affinity.** The Pod requires running on a node where certain other Pods are not running, but all nodes have those Pods. With `requiredDuringScheduling` anti-affinity, the Pod stays Pending. Fix: use `preferred` instead of `required`, or add more nodes.

7. **ResourceQuota exceeded.** If the namespace has a ResourceQuota and the Pod's requests would exceed it, the Pod isn't even created by the controller (the ReplicaSet's events will show the quota error).

### Q56. How do you view logs for a pod that has already crashed?

There are several techniques depending on how the Pod crashed and what logging infrastructure you have:

**`kubectl logs --previous` (most common):**
```bash
kubectl logs <pod-name> -n doctor-app --previous
# For multi-container Pods:
kubectl logs <pod-name> -n doctor-app -c <container-name> --previous
```
The `--previous` flag retrieves logs from the last terminated container instance. Kubelet stores these logs on the node's filesystem, and they're available as long as the Pod object still exists in the API server (even if the container restarted). This is your primary tool.

**Limitation:** `--previous` only shows logs from the *last* terminated container. If the Pod has crash-looped multiple times, you only see the most recent crash's logs. Earlier crashes are lost from this mechanism.

**Centralized logging (production standard):**
In a production cluster, you should have a logging pipeline that collects container stdout/stderr and sends it to a central store:
- **GKE**: Cloud Logging (formerly Stackdriver) is enabled by default. All container logs are shipped to Cloud Logging automatically. You can query historical logs even after Pods are deleted: `gcloud logging read 'resource.type="k8s_container" resource.labels.pod_name="doctor-backend-7f8b9c-x4k2l"' --limit 100`.
- **Self-managed**: Fluentd/Fluentbit DaemonSet → Elasticsearch → Kibana, or Loki + Promtail + Grafana.

**If the Pod object is deleted:**
Once a Pod object is deleted from the API server (e.g., by scaling down or deleting the Deployment), `kubectl logs` no longer works — there's no Pod to query. At this point, your only option is centralized logging. This is why centralized logging is non-negotiable for production clusters.

**Debugging a crashing Pod interactively:**
If you need to inspect the container's filesystem or environment after a crash, use ephemeral debug containers (Kubernetes 1.25+):
```bash
kubectl debug <pod-name> -n doctor-app --copy-to=debug-pod --container=debugger --image=busybox -- sh
```
This creates a copy of the Pod with an additional debug container, sharing the same namespaces. You can examine the filesystem, environment variables, and network state.

### Q57. A Service is not routing traffic to your pods. How do you troubleshoot?

When a Service isn't routing traffic to Pods, systematically check each layer of the routing chain:

**Step 1: Verify the Service exists and has the right configuration.**
```bash
kubectl get svc doctor-backend -n doctor-app -o yaml
```
Check: Is the Service type correct (ClusterIP, NodePort, etc.)? Is the `selector` correct (matches the Pods' labels)? Is the `targetPort` correct (matches the port the container is listening on)?

**Step 2: Verify Endpoints exist.**
```bash
kubectl get endpoints doctor-backend -n doctor-app
```
Endpoints list the Pod IPs that the Service routes to. If the Endpoints list is empty, the Service's selector doesn't match any running Pods. Common mistakes: typo in the selector label (e.g., `app: doctor-backend` vs `app: doctor_backend`), Pods are in a different namespace, or no Pods match the selector.

**Step 3: Verify Pod readiness.**
```bash
kubectl get pods -l app=doctor-backend -n doctor-app
```
A Pod only appears in a Service's Endpoints when its readiness probe passes. If Pods exist but Endpoints are empty, check the readiness probe: `kubectl describe pod <name>` — look for "Readiness probe failed." The Pod is running but not ready, so the Service excludes it.

**Step 4: Verify the Pod is actually listening.**
```bash
kubectl exec -it <pod-name> -n doctor-app -- curl localhost:8000/health
# Or for containers without curl:
kubectl exec -it <pod-name> -n doctor-app -- wget -qO- localhost:8000/health
```
If the application isn't listening on the expected port, the Service can't route to it. Check the container's command and port configuration.

**Step 5: Test from within the cluster.**
```bash
kubectl run curl-test --image=curlimages/curl --rm -it -- curl http://doctor-backend.doctor-app.svc.cluster.local:8000/health
```
This tests the full chain: DNS resolution → Service ClusterIP → kube-proxy routing → Pod. If this works, the issue is outside the cluster (Ingress, firewall). If DNS fails, check CoreDNS (`kubectl get pods -n kube-system -l k8s-app=kube-dns`).

**Step 6: Check NetworkPolicies.**
```bash
kubectl get networkpolicy -n doctor-app
```
A NetworkPolicy might be blocking traffic to or from the Service's Pods. Temporarily remove NetworkPolicies to test (in non-production environments).

### Q58. How do you debug DNS resolution issues within a cluster?

DNS issues in Kubernetes typically manifest as "could not resolve hostname" errors in application logs or `nslookup` failures from within Pods.

**Step 1: Test DNS resolution from a Pod.**
```bash
kubectl run dns-test --image=busybox:1.36 --rm -it -- nslookup doctor-backend.doctor-app.svc.cluster.local
# Or more detailed:
kubectl run dns-test --image=dnsutils --rm -it -- dig doctor-backend.doctor-app.svc.cluster.local
```
If `nslookup` returns the Service's ClusterIP, DNS is working. If it returns `NXDOMAIN` or times out, there's a DNS issue.

**Step 2: Check CoreDNS health.**
```bash
kubectl get pods -n kube-system -l k8s-app=kube-dns
kubectl logs -n kube-system -l k8s-app=kube-dns
```
Are CoreDNS Pods running and ready? Check logs for errors — common issues include: CoreDNS can't reach the API server (check RBAC), CoreDNS Pods are crash-looping (check resource limits — CoreDNS can OOM in large clusters with thousands of Services), or CoreDNS ConfigMap has a misconfigured Corefile.

**Step 3: Verify Pod DNS configuration.**
```bash
kubectl exec -it <pod-name> -n doctor-app -- cat /etc/resolv.conf
```
The output should show `nameserver <CoreDNS-ClusterIP>` and search domains including `doctor-app.svc.cluster.local svc.cluster.local cluster.local`. If the nameserver is wrong or search domains are missing, check the Pod's `dnsPolicy` field. The default `ClusterFirst` should use CoreDNS. If someone set `dnsPolicy: Default`, the Pod uses the node's DNS, which doesn't know about Kubernetes Services.

**Step 4: Check the Service exists and is in the right namespace.**
```bash
kubectl get svc -n doctor-app
```
DNS resolution of `doctor-backend` only works if the Service `doctor-backend` exists in the same namespace (or you use the fully qualified name `doctor-backend.doctor-app.svc.cluster.local`). A common mistake: the Pod is in namespace `doctor-app` but the Service was accidentally created in `default`.

**Step 5: Check for DNS policy or NetworkPolicy blocking DNS traffic.**
NetworkPolicies that restrict egress can block DNS queries. DNS uses UDP port 53 to CoreDNS's ClusterIP. If you have a default-deny egress policy, you must explicitly allow egress to the `kube-system` namespace (or to the CoreDNS ClusterIP) on port 53.

```yaml
# Allow DNS egress in a default-deny namespace
egress:
  - to:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: kube-system
    ports:
      - protocol: UDP
        port: 53
      - protocol: TCP
        port: 53
```

**Step 6: Check the CoreDNS ConfigMap.**
```bash
kubectl get configmap coredns -n kube-system -o yaml
```
Verify the `Corefile` configuration. Common issues: incorrect upstream DNS (the `forward` directive), missing or misconfigured `kubernetes` plugin, or custom entries that conflict.

> **AI Doctor Example:** The `doctor-backend` Pod fails to connect to PostgreSQL with "could not resolve hostname 'postgres'." Debugging: (1) `kubectl exec` into the Pod and run `nslookup postgres` — it times out. (2) Check `/etc/resolv.conf` — nameserver is correct. (3) `kubectl get svc postgres -n doctor-app` — the Service exists. (4) `kubectl get networkpolicy -n doctor-app` — there's a default-deny egress policy without a DNS exception. Adding a DNS egress rule to the NetworkPolicy fixes the issue immediately.

---

## Summary: Knowledge Validation Tips

1. **Know the fundamentals cold.** Questions 1–8 (core concepts) are foundational to all Kubernetes work. Be able to explain Pods, Deployments, Services, and StatefulSets without hesitation.

2. **Debugging questions carry the most weight.** Questions 44–58 test real-world competence. Systematic troubleshooting matters more than memorized answers. Always start with `kubectl get`, then `kubectl describe`, then `kubectl logs`.

3. **Connect concepts to real applications.** Don't just define what an Ingress is — explain why you'd use it instead of multiple LoadBalancer Services for a multi-service application.

4. **Know the failure modes.** For every feature (Services, Deployments, PVCs), know what happens when things go wrong. "What happens when a readiness probe fails?" "What happens when a PVC can't bind?"

5. **Practice with kubectl.** The best preparation is running a local cluster (minikube, kind) and deliberately breaking things — deploy a Pod with a bad image, misconfigure a Service selector, create a NetworkPolicy that blocks DNS — then practice debugging.

6. **GKE specifics matter for GCP work.** If working with GCP, know Autopilot vs Standard, Workload Identity, Binary Authorization, and VPC-native networking. These are differentiators from generic Kubernetes knowledge.

---

> **Next:** [09-REFERENCE-CARD.md](./09-REFERENCE-CARD.md) — Quick-reference cheat sheet for kubectl commands, YAML snippets, and common patterns.
