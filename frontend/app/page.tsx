"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import AdminDashboard from "../components/AdminDashboard";
import AuthPanel from "../components/AuthPanel";
import HeadlinesGrid from "../components/HeadlinesGrid";
import PersonalizationPanel from "../components/PersonalizationPanel";
import ResearchWorkspace from "../components/ResearchWorkspace";
import SearchForm from "../components/SearchForm";
import SearchResults from "../components/SearchResults";
import SportsWorkspace from "../components/SportsWorkspace";
import UserDashboard from "../components/UserDashboard";

import { useAdmin } from "../hooks/useAdmin";
import { useAuth } from "../hooks/useAuth";
import { useHeadlines } from "../hooks/useHeadlines";
import { usePersonalization } from "../hooks/usePersonalization";
import { useResearch } from "../hooks/useResearch";
import { useSearch } from "../hooks/useSearch";
import { useSports } from "../hooks/useSports";
import type { Category } from "../types/api";

const categoryLabels: Record<Category, string> = { tech: "Tech", research: "Research", sports: "Sports", general: "General" };

export default function HomePage() {
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [userId, setUserId] = useState("default");

  const apiUrl = useMemo(() => {
    const base = process.env.NEXT_PUBLIC_API_URL
      || (typeof window !== "undefined" && !["localhost", "127.0.0.1"].includes(window.location.hostname) ? "/api" : "http://127.0.0.1:8000");
    // All product endpoints live under /v1 — health/metrics stay at root
    return `${base}/v1`;
  }, []);

  const auth = useAuth(apiUrl, { onError: setError, onInfo: setInfo });
  const activeUserId = auth.session?.user?.user_id || userId;

  const headlines = useHeadlines(apiUrl, 7, { onError: setError });
  const search = useSearch(apiUrl, activeUserId, auth.apiFetch, { onError: setError, onInfo: setInfo });
  const personalization = usePersonalization(apiUrl, activeUserId, auth.apiFetch, { onError: setError, onInfo: setInfo });
  const sports = useSports(apiUrl);
  const research = useResearch(apiUrl);
  const admin = useAdmin(auth.session?.user?.is_admin, auth.apiFetch, { onError: setError, onInfo: setInfo });

  return (
    <main className="page-shell">
      <nav className="top-nav" aria-label="Category navigation">
        <p className="badge">SignalScope AI</p>
        <div className="nav-links">
          {(Object.entries(categoryLabels) as [Category, string][]).map(([slug, label]) => (
            <Link key={slug} href={`/category/${slug}`} className="text-link">{label}</Link>
          ))}
        </div>
      </nav>

      <section className="hero hero-split">
        <div>
          <h1>Search live signals. Explain what changed.</h1>
          <p className="subtitle">One workspace for tech news, research, sports, and world coverage with grounded answers, saved sessions, and admin-aware source controls.</p>
        </div>
        <AuthPanel
          session={auth.session} authMode={auth.authMode} setAuthMode={auth.setAuthMode}
          authForm={auth.authForm} setAuthForm={auth.setAuthForm}
          resetEmail={auth.resetEmail} setResetEmail={auth.setResetEmail}
          resetToken={auth.resetToken} setResetToken={auth.setResetToken}
          resetPassword={auth.resetPassword} setResetPassword={auth.setResetPassword}
          verificationPreview={auth.verificationPreview} resetPreview={auth.resetPreview}
          submitAuth={auth.submitAuth} logout={auth.logout}
          requestVerification={auth.requestVerification} verifyEmailFromPreview={auth.verifyEmailFromPreview}
          requestPasswordReset={auth.requestPasswordReset} confirmPasswordReset={auth.confirmPasswordReset}
        />
      </section>

      {info && <p className="info-banner" role="status" aria-live="polite">{info}</p>}
      {error && <p className="error" role="alert" aria-live="assertive">{error}</p>}

      <HeadlinesGrid
        headlines={headlines.headlines} headlinesUpdatedAt={headlines.headlinesUpdatedAt}
        headlinesLoading={headlines.headlinesLoading} loadHeadlines={headlines.loadHeadlines}
        onHeadlineClick={search.useHeadlineQuery} onBookmark={personalization.addBookmark}
      />

      <SearchForm
        query={search.query} setQuery={search.setQuery}
        compareAgainst={search.compareAgainst} setCompareAgainst={search.setCompareAgainst}
        topK={search.topK} setTopK={search.setTopK}
        mode={search.mode} setMode={search.setMode}
        explanationFormat={search.explanationFormat} setExplanationFormat={search.setExplanationFormat}
        timeline={search.timeline} setTimeline={search.setTimeline}
        selected={search.selected} toggleCategory={search.toggleCategory}
        recencyDays={search.recencyDays} setRecencyDays={search.setRecencyDays}
        sortBy={search.sortBy} setSortBy={search.setSortBy}
        sourceFilterText={search.sourceFilterText} setSourceFilterText={search.setSourceFilterText}
        sourceTypesSelected={search.sourceTypesSelected} toggleSourceType={search.toggleSourceType}
        activeUserId={activeUserId} setUserId={setUserId} session={auth.session}
        loading={search.loading} onSubmit={search.runSearch}
        onRefreshFollows={personalization.refreshFollows} onRefreshAlerts={personalization.refreshAlerts}
        onFetchSportsInsights={() => sports.fetchSportsInsights(search.query)}
        onFetchSportsDashboard={() => sports.fetchSportsDashboard(search.recencyDays)}
        onFetchResearchInsights={() => research.fetchResearchInsights(search.query)}
        onFetchResearchPapers={() => research.fetchResearchPapers(search.query, search.recencyDays)}
      />

      <PersonalizationPanel
        followEntity={personalization.followEntity} setFollowEntity={personalization.setFollowEntity}
        followed={personalization.followed} onAddFollow={personalization.addFollow}
        alertQuery={personalization.alertQuery} setAlertQuery={personalization.setAlertQuery}
        alerts={personalization.alerts}
        onCreateAlert={() => personalization.createAlert(personalization.alertQuery, search.selected)}
        delivery={personalization.delivery} setDelivery={personalization.setDelivery}
        deliveryTest={personalization.deliveryTest}
        onSaveDelivery={personalization.saveDelivery} onTestDelivery={personalization.testDelivery}
        bookmarks={personalization.bookmarks} onRemoveBookmark={personalization.removeBookmark}
        activeUserId={activeUserId}
      />

      <UserDashboard
        session={auth.session}
        history={search.history} onHistorySelect={search.setQuery}
        savedSessions={search.savedSessions}
        sessionLabel={search.sessionLabel} setSessionLabel={search.setSessionLabel}
        onSaveSession={search.saveCurrentSession} result={search.result}
        followed={personalization.followed} alerts={personalization.alerts} bookmarks={personalization.bookmarks}
      />

      <SearchResults
        result={search.result} loading={search.loading} appliedFiltersText={search.appliedFiltersText} session={auth.session}
        followUpQuestion={search.followUpQuestion} setFollowUpQuestion={search.setFollowUpQuestion}
        followUpResponse={search.followUpResponse}
        sessionLabel={search.sessionLabel} setSessionLabel={search.setSessionLabel}
        onSaveSession={search.saveCurrentSession}
        onCreateAlert={(q) => personalization.createAlert(q || search.query, search.selected)}
        onSetFollowEntity={() => personalization.setFollowEntity(search.query)}
        onBookmark={personalization.addBookmark}
        onExplainPaper={(paper) => research.explainPaper(paper, search.mode)}
        onResetFilters={search.resetSearchFilters}
        onExpandRecency={() => search.setRecencyDays(30)}
        onSuggestedQuery={search.useSuggestedQuery}
        onRunFollowUp={search.runFollowUp}
      />

      <section className="two-grid">
        <SportsWorkspace
          sportsTeam={sports.sportsTeam} setSportsTeam={sports.setSportsTeam}
          sportsInsight={sports.sportsInsight} sportsDashboard={sports.sportsDashboard}
          onLoadTeam={() => sports.fetchSportsDashboard(search.recencyDays)}
        />
        <ResearchWorkspace
          researchInsight={research.researchInsight} researchPapers={research.researchPapers}
          explainedPaper={research.explainedPaper} paperComparison={research.paperComparison}
          comparePapers={research.comparePapers}
          onExplainPaper={(paper) => research.explainPaper(paper, search.mode)}
          onToggleComparePaper={research.toggleComparePaper}
        />
      </section>

      <AdminDashboard
        session={auth.session} adminData={admin.adminData} adminSources={admin.adminSources}
        adminLoading={admin.adminLoading}
        reingestTopic={admin.reingestTopic} setReingestTopic={admin.setReingestTopic}
        onRefresh={admin.loadAdminData} onToggleSource={admin.toggleSourceEnabled}
        onReingest={admin.triggerReingest} selected={search.selected}
      />
    </main>
  );
}
