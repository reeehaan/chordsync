# Bootstrap: the two buckets everything else depends on

These small Terraform setups manage buckets that the main stack in `../aws` relies on
but must not be able to replace or delete. Run each from its own folder. Their state
lives in the Terraform state bucket under `chordsync/bootstrap/`.

| Folder | Manages | Why separate |
| --- | --- | --- |
| `model-backup/` | A protected, versioned copy of the model files | The main stack once replaced the artifacts bucket and the models with it |
| `state-bucket/` | The Terraform state bucket's policy and lifecycle | The state bucket was created by hand and had no protection |

Both exempt three principals from the "destructive action" denies: the
`ChordSyncTerraformRole`, the IAM user `rehan`, and the account root. If a policy ever
locks you out, the account root can delete the bucket policy.

Order: `model-backup`, then `state-bucket`. Show the plan before applying each.
