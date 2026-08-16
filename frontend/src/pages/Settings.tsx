import { useEffect, useState } from 'react';
import { api, ApiError } from '../api/client';
import type { Health, Settings } from '../types/api';
import { toast } from '../store/toast';
import { cn, formatDateTime } from '../utils/format';
import { useApi } from '../utils/hooks';
import { Button, Input, Toggle } from '../components/controls';
import { Card, EmptyState, ErrorState, PageHeader, Skeleton, Spinner } from '../components/ui';
import { Badge } from '../components/badges';

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-white/5 py-2.5 last:border-0">
      <span className="text-xs text-zinc-500">{label}</span>
      <span className="text-sm text-zinc-200">{value}</span>
    </div>
  );
}

export default function Settings() {
  const settings = useApi<Settings>(() => api.get('/settings'), []);
  const health = useApi<Health>(() => api.get('/health'), []);

  // LLM Key
  const [apiKey, setApiKey] = useState('');
  const [keySaving, setKeySaving] = useState(false);

  // 通知设置
  const [emailEnabled, setEmailEnabled] = useState(false);
  const [emailTo, setEmailTo] = useState('');
  const [notifSaving, setNotifSaving] = useState(false);

  useEffect(() => {
    if (settings.data) {
      setEmailEnabled(settings.data.notifications.email_enabled);
      setEmailTo(settings.data.notifications.email_to ?? '');
    }
  }, [settings.data]);

  const saveKey = async () => {
    if (!apiKey.trim()) {
      toast('请输入 API Key', 'error');
      return;
    }
    setKeySaving(true);
    try {
      await api.post('/settings/keys', { deepseek_api_key: apiKey.trim() });
      toast('API Key 已加密保存', 'success');
      setApiKey('');
      settings.reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '保存失败', 'error');
    } finally {
      setKeySaving(false);
    }
  };

  const deleteKey = async () => {
    try {
      await api.delete('/settings/keys/deepseek');
      toast('已清除自定义 API Key', 'info');
      settings.reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '清除失败', 'error');
    }
  };

  const saveNotifications = async () => {
    setNotifSaving(true);
    try {
      await api.put('/settings', {
        notifications: { email_enabled: emailEnabled, email_to: emailTo },
      });
      toast('通知设置已保存', 'success');
      settings.reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '保存失败', 'error');
    } finally {
      setNotifSaving(false);
    }
  };

  const llm = settings.data?.llm;
  const notif = settings.data?.notifications;

  return (
    <div className="space-y-4">
      <PageHeader title="设置" desc="LLM、通知与数据源配置" />

      {settings.loading && (
        <div className="grid gap-3 lg:grid-cols-2">
          <Skeleton className="h-64 rounded-xl" />
          <Skeleton className="h-64 rounded-xl" />
        </div>
      )}
      {settings.error && <ErrorState message={settings.error} onRetry={settings.reload} />}

      {!settings.loading && !settings.error && settings.data && (
        <>
          {/* LLM */}
          <div className="grid gap-3 lg:grid-cols-2">
            <Card title="LLM 配置（DeepSeek）">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="blue">{llm?.provider ?? '--'}</Badge>
                <Badge tone="purple">{llm?.model ?? '--'}</Badge>
                {llm?.has_api_key_env && <Badge tone="green">已配置环境变量 Key</Badge>}
                {llm?.has_user_key && <Badge tone="amber">已配置用户自定义 Key</Badge>}
              </div>
              <div className="mt-4">
                <InfoRow label="接口地址" value={<span className="num-mono text-xs">{llm?.base_url ?? '--'}</span>} />
                <InfoRow
                  label="模型"
                  value={<span className="num-mono text-xs">{llm?.model ?? '--'}</span>}
                />
                <InfoRow
                  label="状态"
                  value={
                    llm?.has_api_key_env || llm?.has_user_key ? (
                      <Badge tone="green">可用</Badge>
                    ) : (
                      <Badge tone="amber">未配置 Key（AI 对话将降级为量化引擎）</Badge>
                    )
                  }
                />
              </div>
              <div className="mt-4 border-t border-white/5 pt-4">
                <div className="mb-1 text-xs text-zinc-500">设置用户 DeepSeek API Key（后端加密存储，永不回显）</div>
                <div className="flex gap-2">
                  <Input
                    type="password"
                    value={apiKey}
                    onChange={setApiKey}
                    placeholder="sk-..."
                    className="font-mono"
                  />
                  <Button variant="primary" size="md" onClick={() => void saveKey()} disabled={keySaving}>
                    {keySaving ? <Spinner className="h-4 w-4" /> : '保存'}
                  </Button>
                </div>
                {llm?.has_user_key && (
                  <button
                    onClick={() => void deleteKey()}
                    className="mt-2 text-[11px] text-zinc-600 transition hover:text-red-400"
                  >
                    清除自定义 Key（将回退到环境变量 Key）
                  </button>
                )}
              </div>
            </Card>

            {/* 通知设置 */}
            <Card title="通知设置">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm text-zinc-200">邮件通知</div>
                    <div className="mt-0.5 text-[11px] text-zinc-600">
                      分析报告与系统通知推送到邮箱
                    </div>
                  </div>
                  <Toggle checked={emailEnabled} onChange={setEmailEnabled} />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-zinc-500">接收邮箱</label>
                  <Input value={emailTo} onChange={setEmailTo} placeholder="you@example.com" />
                </div>
                <div>
                  <div className="mb-1 text-xs text-zinc-500">当前启用渠道</div>
                  <div className="flex gap-1.5">
                    {(notif?.channels ?? []).map((c) => (
                      <Badge key={c}>{c === 'in_app' ? '站内通知' : c}</Badge>
                    ))}
                    {(notif?.channels ?? []).length === 0 && <span className="text-xs text-zinc-600">无</span>}
                  </div>
                </div>
                <Button variant="primary" size="sm" onClick={() => void saveNotifications()} disabled={notifSaving}>
                  {notifSaving ? <Spinner className="h-3.5 w-3.5" /> : '保存通知设置'}
                </Button>
              </div>
            </Card>
          </div>

          {/* 数据同步与来源透明 */}
          <div className="grid gap-3 lg:grid-cols-2">
            <Card title="数据同步">
              <InfoRow
                label="行情快照间隔"
                value={<span className="num-mono text-xs">{settings.data.sync.quote_interval_minutes} 分钟</span>}
              />
              <InfoRow label="时区" value={<span className="num-mono text-xs">{settings.data.timezone}</span>} />
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {health.data ? (
                  <>
                    <Badge tone={health.data.status === 'ok' ? 'green' : 'amber'}>
                      服务 {health.data.status}
                    </Badge>
                    <Badge tone={health.data.db === 'ok' ? 'green' : 'red'}>数据库 {health.data.db}</Badge>
                    <Badge tone="blue">数据源 {health.data.data_provider}</Badge>
                    <Badge tone={health.data.llm === 'configured' ? 'green' : 'amber'}>
                      LLM {health.data.llm}
                    </Badge>
                  </>
                ) : (
                  <span className="text-xs text-zinc-600">健康检查不可用（后端未启动）</span>
                )}
              </div>
            </Card>

            <Card title="数据来源透明">
              <div className="space-y-2.5 text-xs leading-relaxed text-zinc-400">
                <p>
                  平台所有外部数据均通过 <span className="text-zinc-200">DataProvider</span> 抽象层获取，
                  支持 <span className="text-zinc-200">东方财富（Eastmoney）</span> 实时数据与
                  <span className="text-zinc-200">离线 Mock 演示数据</span>，失败自动降级。
                </p>
                <p>每条数据行保留 source 与 retrieved_at 字段，可在基金详情「数据来源」、AI 对话「数据来源」按钮中追溯。</p>
                <p>
                  LLM 仅在配置 API Key 后启用；未配置时 AI 对话自动降级为
                  <span className="text-amber-400">量化引擎结构化摘要</span>，其余功能不受影响。
                </p>
              </div>
            </Card>
          </div>

          {/* 关于 */}
          <Card title="关于与免责声明">
            <div className="space-y-2.5 text-xs leading-relaxed text-zinc-400">
              <p>
                <span className="font-medium text-zinc-200">基金智能分析预测平台</span>
                —— 面向个人投资者的研究与辅助分析工具。
              </p>
              <p>
                所有评分、预测与 AI 结论均为<strong className="text-zinc-200">概率估计与情景分析</strong>，
                基于历史数据与量化模型，不构成投资建议，不承诺任何收益，不宣称能够准确预测市场。
              </p>
              <p>投资有风险，入市需谨慎。请结合自身情况独立判断。</p>
              <p className="pt-1 text-[10px] text-zinc-600">
                系统时间：{formatDateTime(new Date().toISOString())} · 后端时区 {settings.data.timezone}
              </p>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
