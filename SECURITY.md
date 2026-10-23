# Security policy / 安全说明

## Private reporting / 私下报告

Report suspected vulnerabilities through GitHub private vulnerability reporting: open the repository's **Security** tab and choose **Report a vulnerability**, or go directly to <https://github.com/chaw1/datakeel/security/advisories/new>. The report is visible only to the maintainer and to you. Do not open a public issue or pull request for an unpatched vulnerability.

疑似漏洞请通过 GitHub 私密漏洞报告提交：在仓库 **Security** 页点 **Report a vulnerability**，或直接打开 <https://github.com/chaw1/datakeel/security/advisories/new>。报告只有维护者和你本人能看到。尚未修复的漏洞不要发公开 issue 或 PR。

Include the affected version or commit, vulnerable component, prerequisites, a minimal reproduction using generated data, observed impact and any suggested mitigation. Redact secrets, personal information and unrelated data. Share exploit details only in the private advisory.

报告请包含受影响版本或提交、组件、触发前提、使用生成数据的最小复现、实际影响及已有缓解建议。删除密钥、个人信息和无关数据；利用细节只写在私密报告里。

The maintainer will confirm receipt, assess scope, agree on a fix and disclosure plan with the reporter, and publish remediation guidance when ready. No response-time guarantee or bounty program is currently offered. Avoid disclosing an unpatched vulnerability publicly before coordinating with the maintainer.

维护者收到报告后会确认收件、评估影响范围，并与报告者确定修复与披露安排；修复就绪后公布处理建议。目前不承诺响应时限，也未设漏洞奖励计划。未经协调，请勿公开尚未修复漏洞的细节。

## Supported versions / 支持范围

Security fixes target the latest release and the current development branch. Older releases do not have a separate security-maintenance commitment; reproduce on the latest release when practical and upgrade to the version carrying the fix.

安全修复面向最新发布版本和当前开发分支。旧版本没有单独的安全维护承诺；条件允许时请在最新版本复现，并升级到包含修复的版本。

## Safe testing / 安全验证

Test only on your own local instance or an environment for which you have explicit authorization. Use synthetic data and fake model providers. Do not access other users' files, tenant data, services or credentials. Avoid destructive testing on shared resources.

仅在自己的本地实例或明确获授权的环境中测试，使用合成数据和假模型服务。不得访问他人的文件、租户数据、服务或凭证，不在共享资源上做破坏性验证。
