import { Navigate, useParams } from 'react-router-dom';
import { paths } from '@/routes/paths';

// ----------------------------------------------------------------------

/** Legacy route — redirects to the Study dashboard tab. */
export default function StudyCompanionPage() {
  const { documentId = '' } = useParams<{ documentId: string }>();
  return <Navigate to={paths.dashboard.studyCompanion(documentId)} replace />;
}
