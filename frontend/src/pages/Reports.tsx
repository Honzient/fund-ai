import { useEffect, useState } from 'react';
import { api, ApiError } from '../api/client';
import type { FundSummary, ReportDetail, ReportSummary, Schedule, ScheduleInput } from '../types/api';
import { toast } from '../store/toast';
import { cn, formatDateTime } from '../utils/format';
import { useApi, useDebounce } from '../utils/hooks';
import { Button, Checkbox, Input, Select, Toggle } from '../components/controls';
import { Card, EmptyState, ErrorState, PageHeader, Skeleton, Spinner } from '../components/ui';
import { Badge } from '../components/badges';
import { Modal } from '../components/overlay';
import Markdown from '../components/Markdown';
import { IconPlus, IconRefresh, IconTrash } from '../components/icons';

const SCHEDULE_TYPES: { value: string; label: string }[] = [
  { value: 'daily', label: '每日' },
  { value: 'weekly', label: '每周' },
  { value: 'monthly', label: '每月' },
  { value: 'cron', label: 'Cron 表达式' },
];

const CHANNELS = [
  { value: 'in_app', label: '站内通知' },
  { value: 'email', label: '邮件' },
];

const WEEKDAYS = [
  { value: '0', label: '周一' },
  { value: '1', label: '周二' },
  { value: '2', label: '周三' },
  { value: '3', label: '周四' },
  { value: '4', label: '周五' },
  { value: '5', label: '周六' },
  { value: '6', label: '周日' },
];

function ScheduleFormModal({
  open,
  onClose,
  schedule,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  schedule: Schedule | null;
  onSaved: () => void;
}) {
  const [name, setName] = useState('');
  const [scheduleType, setScheduleType] = useState('daily');
  const [timeOfDay, setTimeOfDay] = useState('16:00');
  const [dayOfWeek, setDayOfWeek] = useState('0');
  const [dayOfMonth, setDayOfMonth] = useState('1');
  const [cronExpression, setCronExpression] = useState('0 16 * * *');
  const [fundSearch, setFundSearch] = useState('');
  const [fundResults, setFundResults] = useState<FundSummary[]>([]);
  const [fundIds, setFundIds] = useState<string[]>([]);
  const [channels, setChannels] = useState<string[]>(['in_app']);
  const [llmSummary, setLlmSummary] = useState(true);
  const [enabled, setEnabled] = useState(true);
  const [saving, setSaving] = useState(false);
  const debouncedSearch = useDebounce(fundSearch, 300);

  useEffect(() => {
    if (!open) return;
    setName(schedule?.name ?? '');
    setScheduleType(schedule?.schedule_type ?? 'daily');
    setTimeOfDay(schedule?.time_of_day ?? '16:00');
    setDayOfWeek(String(schedule?.day_of_week ?? 0));
    setDayOfMonth(String(schedule?.day_of_month ?? 1));
    setCronExpression(schedule?.cron_expression ?? '0 16 * * *');
    setFundIds(schedule?.fund_ids ?? []);
    setChannels(schedule?.notification_channels ?? ['in_app']);
    setLlmSummary(schedule?.llm_summary ?? true);
    setEnabled(schedule?.enabled ?? true);
  }, [open, schedule]);

  useEffect(() => {
    if (!debouncedSearch.trim()) {
      setFundResults([]);
      return;
    }
    let alive = true;
    api
      .get<FundSummary[]>('/funds', { search: debouncedSearch.trim(), limit: 10 })
      .then((list) => {
        if (alive) setFundResults(list ?? []);
      })
      .catch(() => {
        if (alive) setFundResults([]);
      });
    return () => {
      alive = false;
    };
  }, [debouncedSearch]);

  const toggleChannel = (c: string) => {
    setChannels((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]));
  };

  const toggleFund = (code: string) => {
    setFundIds((prev) => (prev.includes(code) ? prev.filter((x) => x !== code) : [...prev, code]));
  };

  const save = async () => {
    if (!name.trim()) {
      toast('请填写任务名称', 'error');
      return;
    }
    if (fundIds.length === 0) {
      toast('请至少选择一只基金', 'error');
      return;
    }
    const body: ScheduleInput = {
      name: name.trim(),
      schedule_type: scheduleType as ScheduleInput['schedule_type'],
      time_of_day: scheduleType !== 'cron' ? timeOfDay : undefined,
      day_of_week: scheduleType === 'weekly' ? Number(dayOfWeek) : undefined,
      day_of_month: scheduleType === 'monthly' ? Number(dayOfMonth) : undefined,
      cron_expression: scheduleType === 'cron' ? cronExpression : undefined,
      fund_ids: fundIds,
      enabled,
      notification_channels: channels,
      llm_summary: llmSummary,
    };
    setSaving(true);
    try {
      if (schedule) {
        await api.patch(`/schedules/${schedule.id}`, body);
        toast('任务已更新', 'success');
      } else {
        await api.post('/schedules', body);
        toast('任务已创建', 'success');
      }
      onSaved();
      onClose();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '保存失败', 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={schedule ? `编辑任务：${schedule.name}` : '新建定时分析任务'}
      width="max-w-2xl"
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>
            取消
          </Button>
          <Button variant="primary" size="sm" onClick={() => void save()} disabled={saving}>
            {saving ? <Spinner className="h-3.5 w-3.5" /> : '保存'}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div>
          <label className="mb-1 block text-xs text-zinc-500">任务名称</label>
          <Input value={name} onChange={setName} placeholder="如：每周基金组合分析" />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs text-zinc-500">调度类型</label>
            <Select
              value={scheduleType}
              onChange={setScheduleType}
              options={SCHEDULE_TYPES}
              className="w-full"
            />
          </div>
          {scheduleType !== 'cron' && (
            <div>
              <label className="mb-1 block text-xs text-zinc-500">执行时间（HH:mm）</label>
              <Input type="time" value={timeOfDay} onChange={setTimeOfDay} />
            </div>
          )}
        </div>
        {scheduleType === 'weekly' && (
          <div>
            <label className="mb-1 block text-xs text-zinc-500">星期</label>
            <Select value={dayOfWeek} onChange={setDayOfWeek} options={WEEKDAYS} className="w-full" />
          </div>
        )}
        {scheduleType === 'monthly' && (
          <div>
            <label className="mb-1 block text-xs text-zinc-500">每月第几天（1-31）</label>
            <Input
              type="number"
              value={dayOfMonth}
              onChange={(v) => setDayOfMonth(v.replace(/\D/g, ''))}
              placeholder="1"
            />
          </div>
        )}
        {scheduleType === 'cron' && (
          <div>
            <label className="mb-1 block text-xs text-zinc-500">Cron 表达式</label>
            <Input value={cronExpression} onChange={setCronExpression} placeholder="0 16 * * *" />
            <p className="mt-1 text-[10px] text-zinc-600">
              例：每天 16:00 → 0 16 * * *；每周一 9:00 → 0 9 * * 1
            </p>
          </div>
        )}
        <div>
          <label className="mb-1 block text-xs text-zinc-500">选择基金</label>
          <Input
            value={fundSearch}
            onChange={setFundSearch}
            placeholder="搜索并勾选要分析的基金"
          />
          <div className="mt-2 flex max-h-32 flex-wrap gap-1.5 overflow-y-auto">
            {fundResults.map((f) => (
              <label
                key={f.fund_code}
                className={cn(
                  'inline-flex cursor-pointer items-center gap-1.5 rounded-lg border px-2 py-1 text-xs transition',
                  fundIds.includes(f.fund_code)
                    ? 'border-accent/60 bg-accent/10 text-accent'
                    : 'border-white/10 text-zinc-300',
                )}
              >
                <Checkbox
                  checked={fundIds.includes(f.fund_code)}
                  onChange={() => toggleFund(f.fund_code)}
                />
                <span className="max-w-36 truncate">{f.fund_name}</span>
                <span className="num-mono text-[10px] text-zinc-600">{f.fund_code}</span>
              </label>
            ))}
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {fundIds.map((code) => (
              <span
                key={code}
                className="num-mono inline-flex items-center gap-1 rounded bg-accent/10 px-2 py-0.5 text-[11px] text-accent"
              >
                {code}
                <button onClick={() => toggleFund(code)} className="text-accent/60 hover:text-red-400">
                  ✕
                </button>
              </span>
            ))}
            {fundIds.length === 0 && <span className="text-[11px] text-zinc-600">未选择基金</span>}
          </div>
        </div>
        <div>
          <label className="mb-1.5 block text-xs text-zinc-500">通知渠道</label>
          <div className="flex flex-wrap gap-3">
            {CHANNELS.map((c) => (
              <Checkbox
                key={c.value}
                checked={channels.includes(c.value)}
                onChange={() => toggleChannel(c.value)}
                label={c.label}
              />
            ))}
          </div>
        </div>
        <div className="flex items-center gap-6">
          <Toggle checked={llmSummary} onChange={setLlmSummary} label="启用 LLM 摘要" />
          <Toggle checked={enabled} onChange={setEnabled} label="启用任务" />
        </div>
      </div>
    </Modal>
  );
}

export default function Reports() {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [schedulesLoading, setSchedulesLoading] = useState(true);
  const [schedulesError, setSchedulesError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Schedule | null>(null);
  const [runningId, setRunningId] = useState<number | null>(null);

  const reports = useApi<ReportSummary[]>(() => api.get('/reports'), []);
  const [viewReport, setViewReport] = useState<ReportSummary | null>(null);
  const [reportDetail, setReportDetail] = useState<ReportDetail | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [viewMode, setViewMode] = useState<'md' | 'html'>('md');
  const [generating, setGenerating] = useState(false);

  const loadSchedules = () => {
    setSchedulesLoading(true);
    setSchedulesError(null);
    api
      .get<Schedule[]>('/schedules')
      .then((list) => setSchedules(list ?? []))
      .catch((e) => setSchedulesError(e instanceof ApiError ? e.message : '加载失败'))
      .finally(() => setSchedulesLoading(false));
  };

  useEffect(() => {
    loadSchedules();
  }, []);

  const toggleEnabled = async (s: Schedule) => {
    try {
      await api.patch(`/schedules/${s.id}`, { enabled: !s.enabled });
      loadSchedules();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '操作失败', 'error');
    }
  };

  const deleteSchedule = async (s: Schedule) => {
    try {
      await api.delete(`/schedules/${s.id}`);
      toast('任务已删除', 'info');
      loadSchedules();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '删除失败', 'error');
    }
  };

  const runNow = async (s: Schedule) => {
    setRunningId(s.id);
    try {
      const res = await api.post<{ task_id: string; status: string }>(`/schedules/${s.id}/run`);
      toast(`已触发运行（${res.task_id}）`, 'success');
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '触发失败', 'error');
    } finally {
      setRunningId(null);
    }
  };

  const generateReport = async () => {
    setGenerating(true);
    try {
      const res = await api.post<{ task_id: string; status: string }>('/reports/generate');
      toast(`已提交报告生成任务（${res.task_id}）`, 'success');
      window.setTimeout(() => reports.reload(), 1500);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '生成失败', 'error');
    } finally {
      setGenerating(false);
    }
  };

  const openReport = async (r: ReportSummary) => {
    setViewReport(r);
    setReportDetail(null);
    setReportLoading(true);
    setViewMode('md');
    try {
      const d = await api.get<ReportDetail>(`/reports/${r.id}`);
      setReportDetail(d);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '加载报告失败', 'error');
    } finally {
      setReportLoading(false);
    }
  };

  const typeLabel = (s: Schedule) => {
    switch (s.schedule_type) {
      case 'daily':
        return `每日 ${s.time_of_day ?? ''}`;
      case 'weekly':
        return `每周${['一', '二', '三', '四', '五', '六', '日'][s.day_of_week ?? 0] ?? ''} ${s.time_of_day ?? ''}`;
      case 'monthly':
        return `每月${s.day_of_month ?? 1}日 ${s.time_of_day ?? ''}`;
      case 'cron':
        return s.cron_expression ?? 'cron';
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="定时报告"
        desc="定时分析任务与生成报告管理"
      />

      {/* 定时任务 */}
      <Card
        title="定时分析任务"
        extra={
          <Button
            size="sm"
            variant="primary"
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            <IconPlus size={13} /> 新建任务
          </Button>
        }
        bodyClassName="p-2"
      >
        {schedulesLoading && (
          <div className="space-y-2 p-2">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        )}
        {schedulesError && <ErrorState message={schedulesError} onRetry={loadSchedules} />}
        {!schedulesLoading && schedules.length === 0 && (
          <EmptyState
            title="暂无定时任务"
            desc="创建定时分析任务，系统将按计划生成报告并推送通知"
            icon="⏰"
          />
        )}
        <div className="divide-y divide-white/5">
          {schedules.map((s) => (
            <div key={s.id} className="flex flex-wrap items-center gap-3 px-3 py-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-zinc-100">{s.name}</span>
                  {!s.enabled && <Badge>已停用</Badge>}
                  {s.llm_summary && <Badge tone="blue">LLM 摘要</Badge>}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-zinc-600">
                  <span>{typeLabel(s)}</span>
                  <span className="num-mono">
                    基金：{s.fund_ids.length > 0 ? s.fund_ids.join('、') : '--'}
                  </span>
                  <span>通知：{s.notification_channels.join(' / ') || '无'}</span>
                  {s.last_run_at && <span>上次 {formatDateTime(s.last_run_at)}</span>}
                  {s.next_run_at && <span>下次 {formatDateTime(s.next_run_at)}</span>}
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                <Toggle checked={s.enabled} onChange={() => void toggleEnabled(s)} />
                <Button size="sm" onClick={() => void runNow(s)} disabled={runningId === s.id}>
                  <IconRefresh size={12} className={runningId === s.id ? 'animate-spin' : ''} />
                  立即运行
                </Button>
                <Button size="sm" variant="ghost" onClick={() => { setEditing(s); setFormOpen(true); }}>
                  编辑
                </Button>
                <Button size="sm" variant="danger" onClick={() => void deleteSchedule(s)}>
                  <IconTrash size={12} />
                </Button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* 报告列表 */}
      <Card
        title="生成的报告"
        extra={
          <Button size="sm" onClick={() => void generateReport()} disabled={generating}>
            <IconRefresh size={13} className={generating ? 'animate-spin' : ''} />
            {generating ? '生成中…' : '手动生成报告'}
          </Button>
        }
        bodyClassName="p-2"
      >
        {reports.loading && <Skeleton className="mx-2 h-24" />}
        {reports.error && <ErrorState message={reports.error} onRetry={reports.reload} />}
        {!reports.loading && (reports.data ?? []).length === 0 && (
          <EmptyState title="暂无报告" desc="定时任务运行或手动生成后将在此展示" icon="📄" />
        )}
        <div className="divide-y divide-white/5">
          {(reports.data ?? [])
            .slice()
            .sort((a, b) => (b.generated_at ?? '').localeCompare(a.generated_at ?? ''))
            .map((r) => (
              <button
                key={r.id}
                onClick={() => void openReport(r)}
                className="flex w-full items-center justify-between px-3 py-3 text-left transition hover:bg-white/[0.03]"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm text-zinc-100">{r.title}</div>
                  <div className="mt-0.5 text-[11px] text-zinc-600">{formatDateTime(r.generated_at)}</div>
                </div>
                <div className="flex items-center gap-2">
                  {r.trigger && <Badge tone={r.trigger === 'scheduled' ? 'blue' : 'zinc'}>{r.trigger === 'scheduled' ? '定时' : '手动'}</Badge>}
                  <span className="text-xs text-accent">查看 ›</span>
                </div>
              </button>
            ))}
        </div>
      </Card>

      {formOpen && (
        <ScheduleFormModal
          open={formOpen}
          onClose={() => setFormOpen(false)}
          schedule={editing}
          onSaved={loadSchedules}
        />
      )}

      {/* 报告查看 */}
      <Modal
        open={!!viewReport}
        onClose={() => setViewReport(null)}
        title={viewReport?.title ?? '报告'}
        width="max-w-3xl"
      >
        <div className="mb-3 flex items-center gap-2">
          <div className="inline-flex rounded-md border border-white/10 bg-surface-2 p-0.5">
            <button
              onClick={() => setViewMode('md')}
              className={cn(
                'rounded px-3 py-1 text-xs transition',
                viewMode === 'md' ? 'bg-accent/20 text-accent' : 'text-zinc-400',
              )}
            >
              Markdown
            </button>
            <button
              onClick={() => setViewMode('html')}
              className={cn(
                'rounded px-3 py-1 text-xs transition',
                viewMode === 'html' ? 'bg-accent/20 text-accent' : 'text-zinc-400',
              )}
            >
              HTML
            </button>
          </div>
          <span className="text-[11px] text-zinc-600">{formatDateTime(viewReport?.generated_at)}</span>
        </div>
        {reportLoading && (
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-11/12" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        )}
        {!reportLoading && reportDetail && (
          <div className="max-h-[65vh] overflow-y-auto rounded-lg border border-white/5 bg-surface-2 p-4">
            {viewMode === 'md' ? (
              <Markdown content={reportDetail.content_md ?? '（无 Markdown 内容）'} />
            ) : (
              <div
                className="prose-sm text-sm text-zinc-300"
                dangerouslySetInnerHTML={{
                  __html: reportDetail.content_html ?? '<p>（无 HTML 内容）</p>',
                }}
              />
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
